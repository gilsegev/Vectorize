import time
import traceback
import zipfile
from pathlib import Path
from threading import Thread

from app.config import settings as app_settings
from app.models import JobSettings, JobStatus, SelectionMode
from app.services.image_ops import cleanup_raster, normalize_upload, preprocess
from app.services.siliconflow import FORCED_MODEL, generate_candidates, refine_candidate_with_inking
from app.services.storage import (
    append_run_log,
    job_dir,
    read_metadata,
    update_artifacts,
    update_metadata,
    update_stage_duration,
)
from app.services.tuning import measure_line_diagnostics, score_candidate
from app.services.vectorize import vectorize


class PipelineService:
    def start_job(self, job_id: str, upload_bytes: bytes, original_filename: str) -> None:
        append_run_log(job_id, "low", "Job accepted", original_filename=original_filename, upload_bytes=len(upload_bytes))
        thread = Thread(target=self._run_until_selection_or_complete, args=(job_id, upload_bytes, original_filename), daemon=True)
        thread.start()

    def resume_with_selected_variant(self, job_id: str, candidate_name: str) -> None:
        append_run_log(job_id, "low", "Variant selected by user", candidate=candidate_name)
        thread = Thread(target=self._run_finalize_from_selection, args=(job_id, candidate_name), daemon=True)
        thread.start()

    def refine_and_rerun(self, job_id: str, inking_denoise: float) -> None:
        append_run_log(job_id, "low", "Operator requested refine-and-rerun", inking_denoise=inking_denoise)
        thread = Thread(target=self._run_refine_and_rerun, args=(job_id, inking_denoise), daemon=True)
        thread.start()

    def _run_until_selection_or_complete(self, job_id: str, upload_bytes: bytes, original_filename: str) -> None:
        try:
            metadata = read_metadata(job_id)
            job_settings = JobSettings(**metadata["settings"])
            append_run_log(
                job_id,
                "mid",
                "Pipeline started",
                detail_level=job_settings.detail_level.value,
                num_variants=job_settings.num_variants,
                cleanup_strength=job_settings.cleanup_strength.value,
                log_verbosity=job_settings.log_verbosity.value,
                fabrication_style=job_settings.fabrication_style.value,
                prompt_profile=job_settings.prompt_profile.value,
                selection_mode=job_settings.selection_mode.value,
                benchmark_tag=job_settings.benchmark_tag or "",
                source_image_id=job_settings.source_image_id or "",
                inking_denoise=job_settings.inking_denoise,
                potrace_turdsize=job_settings.potrace_turdsize,
                potrace_opttolerance=job_settings.potrace_opttolerance,
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="ingestion")
            original_path, normalized_path = self._stage_ingest(job_id, upload_bytes)
            update_stage_duration(job_id, "ingestion", time.perf_counter() - start)
            update_artifacts(job_id, original=str(original_path), normalized=str(normalized_path))
            append_run_log(job_id, "mid", "Stage done", stage="ingestion", original=original_path.name, normalized=normalized_path.name)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="preprocessing")
            grayscale_path, edge_map_path, subject_mask_path = self._stage_preprocess(job_id, job_settings)
            update_stage_duration(job_id, "preprocessing", time.perf_counter() - start)
            update_artifacts(
                job_id,
                grayscale=str(grayscale_path),
                edge_map=str(edge_map_path),
                subject_mask=str(subject_mask_path),
            )
            append_run_log(
                job_id,
                "mid",
                "Stage done",
                stage="preprocessing",
                grayscale=grayscale_path.name,
                edge_map=edge_map_path.name,
                subject_mask=subject_mask_path.name,
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="generation")
            append_run_log(
                job_id,
                "mid",
                "Generation request prepared",
                provider=("siliconflow" if app_settings.siliconflow_api_key else "local_mock"),
                configured_model=(FORCED_MODEL if app_settings.siliconflow_api_key else app_settings.siliconflow_model),
                detail_level=job_settings.detail_level.value,
                num_variants=job_settings.num_variants,
            )
            try:
                candidates, generation_trace = self._stage_generate(job_id, job_settings)
            except Exception as gen_exc:
                append_run_log(
                    job_id,
                    "mid",
                    "Generation provider call failed",
                    provider=("siliconflow" if app_settings.siliconflow_api_key else "local_mock"),
                    configured_model=(FORCED_MODEL if app_settings.siliconflow_api_key else app_settings.siliconflow_model),
                    elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                    error=f"{gen_exc.__class__.__name__}: {gen_exc}",
                )
                raise
            update_stage_duration(job_id, "generation", time.perf_counter() - start)
            update_artifacts(job_id, candidates=[str(p) for p in candidates])
            append_run_log(
                job_id,
                "mid",
                "Generation provider call",
                provider=generation_trace.get("provider"),
                configured_model=generation_trace.get("configured_model"),
                resolved_model=generation_trace.get("resolved_model"),
                provider_call_ms=generation_trace.get("provider_call_ms"),
                total_generation_ms=generation_trace.get("total_generation_ms"),
                num_variants_requested=generation_trace.get("num_variants_requested"),
                num_variants_generated=generation_trace.get("num_variants_generated"),
                variant_errors=" | ".join(generation_trace.get("variant_errors", [])[:3]),
                prompt_profile=generation_trace.get("prompt_profile"),
                prompt_version=generation_trace.get("prompt_version"),
            )
            update_metadata(job_id, prompt_version=generation_trace.get("prompt_version"))
            append_run_log(job_id, "mid", "Stage done", stage="generation", candidates=len(candidates))
            append_run_log(
                job_id,
                "high",
                "Generation prompts",
                prompt=generation_trace.get("prompt"),
                negative_prompt=generation_trace.get("negative_prompt"),
                steps=generation_trace.get("steps"),
                guidance_scale=generation_trace.get("guidance_scale"),
                strength=generation_trace.get("strength"),
            )
            append_run_log(job_id, "high", "Candidate files", files=",".join([p.name for p in candidates]))

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="inking")
            try:
                refined_candidates, inking_traces = self._stage_ink_candidates(job_id, candidates, job_settings)
            except Exception as ink_exc:
                append_run_log(
                    job_id,
                    "mid",
                    "Inking provider call failed",
                    provider=("siliconflow" if app_settings.siliconflow_api_key else "local_mock"),
                    configured_model=(FORCED_MODEL if app_settings.siliconflow_api_key else app_settings.siliconflow_model),
                    elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                    error=f"{ink_exc.__class__.__name__}: {ink_exc}",
                )
                raise
            update_stage_duration(job_id, "inking", time.perf_counter() - start)
            artifact_updates: dict[str, object] = {"refined_candidates": [str(p) for p in refined_candidates]}
            if refined_candidates:
                artifact_updates["refined"] = str(refined_candidates[0])
            update_artifacts(job_id, **artifact_updates)
            summary = inking_traces[0] if inking_traces else {}
            append_run_log(
                job_id,
                "mid",
                "Inking provider call",
                provider=summary.get("provider"),
                configured_model=summary.get("configured_model"),
                resolved_model=summary.get("resolved_model"),
                denoising_strength=summary.get("denoising_strength"),
                controlnet_model=summary.get("controlnet_model"),
                prompt_profile=generation_trace.get("prompt_profile"),
                provider_call_ms=summary.get("provider_call_ms"),
                total_inking_ms=round(sum(t.get("total_inking_ms", 0.0) for t in inking_traces), 2),
                refined_candidates=len(refined_candidates),
            )
            append_run_log(job_id, "mid", "Stage done", stage="inking", refined_candidates=len(refined_candidates))
            append_run_log(job_id, "high", "Refined candidate files", files=",".join([p.name for p in refined_candidates]))
            score_rows = self._score_candidates(candidates, refined_candidates)
            score_map = {row["candidate"]: row for row in score_rows}
            update_metadata(job_id, candidate_scores=score_map)
            append_run_log(
                job_id,
                "mid",
                "Candidate scoring computed",
                scored=len(score_rows),
                mode=job_settings.selection_mode.value,
            )

            if job_settings.num_variants > 1:
                if job_settings.selection_mode == SelectionMode.auto and app_settings.enable_auto_selection and score_rows:
                    best = min(score_rows, key=lambda row: float(row["score"]))
                    selected_name = str(best["candidate"])
                    update_metadata(job_id, selected_candidate=selected_name, selection_reason=f"auto_score:{best['score']}")
                    append_run_log(
                        job_id,
                        "low",
                        "Auto-selected candidate",
                        candidate=selected_name,
                        score=best["score"],
                    )
                    self._run_finalize_from_selection(job_id, selected_name)
                    return
                update_metadata(job_id, status=JobStatus.waiting_for_selection, selected_candidate=None)
                append_run_log(job_id, "low", "Paused for user selection")
                return

            update_metadata(job_id, selected_candidate="candidate_1.png", selection_reason="single_variant_default")
            self._run_finalize_from_selection(job_id, "candidate_1.png")
        except Exception as exc:  # noqa: BLE001
            self._set_failed(job_id, exc)

    def _run_finalize_from_selection(self, job_id: str, candidate_name: str) -> None:
        try:
            metadata = read_metadata(job_id)
            candidates = metadata.get("artifacts", {}).get("candidates", [])
            candidate_path = None
            for path in candidates:
                if Path(path).name == candidate_name:
                    candidate_path = Path(path)
                    break
            if candidate_path is None:
                raise ValueError(f"unknown candidate '{candidate_name}'")

            update_metadata(job_id, status=JobStatus.processing, selected_candidate=candidate_name)
            settings = JobSettings(**metadata["settings"])
            if not metadata.get("selection_reason"):
                update_metadata(job_id, selection_reason=f"manual_select:{candidate_name}")
            append_run_log(job_id, "mid", "Finalize pipeline", selected_candidate=candidate_name)

            refined_path = self._resolve_or_create_refined(job_id, candidate_name, candidate_path, metadata)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="cleanup")
            binary_path, preview_path = self._stage_cleanup(job_id, refined_path, settings)
            update_stage_duration(job_id, "cleanup", time.perf_counter() - start)
            update_artifacts(job_id, binary=str(binary_path), cleanup_preview=str(preview_path))
            quality = measure_line_diagnostics(binary_path)
            update_metadata(job_id, quality_diagnostics=quality)
            append_run_log(
                job_id,
                "mid",
                "Stage done",
                stage="cleanup",
                binary=binary_path.name,
                cleanup_preview=preview_path.name,
                small_component_count=quality.get("small_component_count"),
                interior_line_density=quality.get("interior_line_density"),
                face_region_density=quality.get("face_region_density"),
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="vectorization")
            svg_path, preview_svg_path, cnc_metrics = self._stage_vectorize(job_id, binary_path, settings)
            update_stage_duration(job_id, "vectorization", time.perf_counter() - start)
            update_artifacts(job_id, final_svg=str(svg_path), final_preview=str(preview_svg_path))
            update_metadata(job_id, cnc_metrics=cnc_metrics)
            append_run_log(
                job_id,
                "mid",
                "Stage done",
                stage="vectorization",
                final_svg=svg_path.name,
                final_preview=preview_svg_path.name,
                node_count=cnc_metrics.get("node_count"),
                mse_fidelity=cnc_metrics.get("mse_fidelity"),
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="export")
            package_path = self._stage_export_package(job_id)
            update_stage_duration(job_id, "export", time.perf_counter() - start)
            update_artifacts(job_id, package_zip=str(package_path))
            append_run_log(job_id, "mid", "Stage done", stage="export", package_zip=package_path.name)

            update_metadata(job_id, status=JobStatus.completed, error=None)
            append_run_log(job_id, "low", "Job completed successfully")
        except Exception as exc:  # noqa: BLE001
            self._set_failed(job_id, exc)

    def _run_refine_and_rerun(self, job_id: str, inking_denoise: float) -> None:
        try:
            metadata = read_metadata(job_id)
            settings = JobSettings(**metadata["settings"])
            settings.inking_denoise = inking_denoise
            update_metadata(job_id, status=JobStatus.processing, settings=settings.model_dump(), error=None)

            candidates = metadata.get("artifacts", {}).get("candidates", [])
            selected_name = metadata.get("selected_candidate") or "candidate_1.png"
            candidate_path = None
            for path in candidates:
                if Path(path).name == selected_name:
                    candidate_path = Path(path)
                    break
            if candidate_path is None:
                raise ValueError(f"unknown candidate '{selected_name}'")

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="inking_rerun")
            refined_path, inking_trace = self._stage_inking(job_id, candidate_path, settings)
            update_stage_duration(job_id, "inking_rerun", time.perf_counter() - start)
            update_artifacts(job_id, refined=str(refined_path))
            append_run_log(
                job_id,
                "mid",
                "Inking rerun provider call",
                provider=inking_trace.get("provider"),
                denoising_strength=inking_trace.get("denoising_strength"),
                refined=refined_path.name,
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="cleanup")
            binary_path, preview_path = self._stage_cleanup(job_id, refined_path, settings)
            update_stage_duration(job_id, "cleanup", time.perf_counter() - start)
            update_artifacts(job_id, binary=str(binary_path), cleanup_preview=str(preview_path))
            quality = measure_line_diagnostics(binary_path)
            update_metadata(job_id, quality_diagnostics=quality)
            append_run_log(
                job_id,
                "mid",
                "Stage done",
                stage="cleanup",
                binary=binary_path.name,
                cleanup_preview=preview_path.name,
                small_component_count=quality.get("small_component_count"),
                interior_line_density=quality.get("interior_line_density"),
                face_region_density=quality.get("face_region_density"),
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="vectorization")
            svg_path, preview_svg_path, cnc_metrics = self._stage_vectorize(job_id, binary_path, settings)
            update_stage_duration(job_id, "vectorization", time.perf_counter() - start)
            update_artifacts(job_id, final_svg=str(svg_path), final_preview=str(preview_svg_path))
            update_metadata(job_id, cnc_metrics=cnc_metrics)
            append_run_log(
                job_id,
                "mid",
                "Stage done",
                stage="vectorization",
                final_svg=svg_path.name,
                final_preview=preview_svg_path.name,
                node_count=cnc_metrics.get("node_count"),
                mse_fidelity=cnc_metrics.get("mse_fidelity"),
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="export")
            package_path = self._stage_export_package(job_id)
            update_stage_duration(job_id, "export", time.perf_counter() - start)
            update_artifacts(job_id, package_zip=str(package_path))
            append_run_log(job_id, "mid", "Stage done", stage="export", package_zip=package_path.name)

            update_metadata(job_id, status=JobStatus.completed, error=None)
            append_run_log(job_id, "low", "Refine-and-rerun completed")
        except Exception as exc:  # noqa: BLE001
            self._set_failed(job_id, exc)

    def _stage_ingest(self, job_id: str, upload_bytes: bytes) -> tuple[Path, Path]:
        root = job_dir(job_id)
        original = root / "01_input_original.png"
        normalized = root / "02_input_normalized.png"

        original.write_bytes(upload_bytes)
        normalize_upload(original, normalized)
        return original, normalized

    def _stage_preprocess(self, job_id: str, settings: JobSettings) -> tuple[Path, Path, Path]:
        root = job_dir(job_id)
        normalized = root / "02_input_normalized.png"
        grayscale = root / "03_preprocess_grayscale.png"
        edge_map = root / "04_preprocess_edge_map.png"
        subject_mask = root / "05_preprocess_subject_mask.png"
        preprocess(normalized, grayscale, edge_map, settings.detail_level.value, subject_mask)
        return grayscale, edge_map, subject_mask

    def _stage_generate(self, job_id: str, settings: JobSettings) -> tuple[list[Path], dict]:
        root = job_dir(job_id)
        normalized = root / "02_input_normalized.png"
        generation_dir = root
        return generate_candidates(
            normalized,
            generation_dir,
            detail_level=settings.detail_level.value,
            num_variants=settings.num_variants,
            prompt_profile=settings.prompt_profile,
        )

    def _stage_ink_candidates(self, job_id: str, candidates: list[Path], settings: JobSettings) -> tuple[list[Path], list[dict]]:
        root = job_dir(job_id)
        subject_mask = root / "05_preprocess_subject_mask.png"
        refined_paths: list[Path] = []
        traces: list[dict] = []
        for idx, candidate in enumerate(candidates, start=1):
            if len(candidates) == 1:
                refined = root / "05_generation_refined.png"
            else:
                refined = root / f"05_generation_refined_candidate_{idx}.png"
            trace = refine_candidate_with_inking(
                candidate,
                subject_mask,
                refined,
                denoising_strength=settings.inking_denoise,
            )
            refined_paths.append(refined)
            traces.append(trace)
        return refined_paths, traces

    def _resolve_or_create_refined(self, job_id: str, candidate_name: str, candidate_path: Path, metadata: dict) -> Path:
        artifacts = metadata.get("artifacts", {})
        refined_candidates = artifacts.get("refined_candidates", []) or []
        selected_index = self._candidate_index(candidate_name)
        if selected_index is not None and selected_index - 1 < len(refined_candidates):
            selected_refined = Path(refined_candidates[selected_index - 1])
            if selected_refined.exists():
                return selected_refined

        refined = artifacts.get("refined")
        if refined and Path(refined).exists():
            return Path(refined)

        append_run_log(job_id, "low", "Inking artifact missing; running fallback inking", candidate=candidate_name)
        settings = JobSettings(**metadata.get("settings", {}))
        fallback_refined, _trace = self._stage_inking(job_id, candidate_path, settings)
        update_artifacts(job_id, refined=str(fallback_refined))
        return fallback_refined

    def _candidate_index(self, candidate_name: str) -> int | None:
        try:
            stem = Path(candidate_name).stem
            return int(stem.split("_")[-1])
        except Exception:
            return None

    def _stage_inking(self, job_id: str, candidate_path: Path, settings: JobSettings) -> tuple[Path, dict]:
        root = job_dir(job_id)
        subject_mask = root / "05_preprocess_subject_mask.png"
        refined = root / "05_generation_refined.png"
        trace = refine_candidate_with_inking(
            candidate_path,
            subject_mask,
            refined,
            denoising_strength=settings.inking_denoise,
        )
        return refined, trace

    def _stage_cleanup(self, job_id: str, candidate_path: Path, settings: JobSettings) -> tuple[Path, Path]:
        root = job_dir(job_id)
        binary = root / "06_cleanup_binary.png"
        preview = root / "07_cleanup_preview.png"
        subject_mask = root / "05_preprocess_subject_mask.png"
        use_tuned_cleanup = app_settings.enable_tuned_cleanup or (
            settings.cleanup_threshold_bias != 0 or settings.cleanup_min_component_px != 20 or settings.cleanup_speck_morph != 0
        )
        if use_tuned_cleanup:
            cleanup_raster(
                candidate_path,
                binary,
                preview,
                settings.cleanup_strength,
                subject_mask,
                threshold_bias=settings.cleanup_threshold_bias,
                min_component_px=settings.cleanup_min_component_px,
                speck_morph=settings.cleanup_speck_morph,
            )
        else:
            cleanup_raster(candidate_path, binary, preview, settings.cleanup_strength, subject_mask)
        return binary, preview

    def _score_candidates(self, candidates: list[Path], refined_candidates: list[Path]) -> list[dict]:
        rows: list[dict] = []
        for idx, candidate in enumerate(candidates, start=1):
            refined = refined_candidates[idx - 1] if idx - 1 < len(refined_candidates) else candidate
            diagnostics = measure_line_diagnostics(refined)
            row = score_candidate(diagnostics, candidate.name)
            row["refined_file"] = refined.name
            rows.append(row)
        return rows

    def _stage_vectorize(self, job_id: str, binary_path: Path, settings: JobSettings) -> tuple[Path, Path, dict[str, float | int]]:
        root = job_dir(job_id)
        svg_out = root / "08_vector_final.svg"
        preview_out = root / "09_vector_final_preview.png"
        cnc_metrics = vectorize(
            binary_path,
            svg_out,
            preview_out,
            turdsize=settings.potrace_turdsize,
            opttolerance=settings.potrace_opttolerance,
            text_min_component=settings.cleanup_min_component_px,
        )
        return svg_out, preview_out, cnc_metrics

    def _stage_export_package(self, job_id: str) -> Path:
        root = job_dir(job_id)
        svg = root / "08_vector_final.svg"
        art = root / "09_vector_final_preview.png"
        package = root / f"{job_id}_Package.zip"
        with zipfile.ZipFile(package, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            if art.exists():
                zf.write(art, arcname="Artistic_Illustration.png")
            if svg.exists():
                zf.write(svg, arcname="Production_Toolpath_SVG.svg")
        return package

    def _set_failed(self, job_id: str, exc: Exception) -> None:
        message = f"{exc.__class__.__name__}: {exc}"
        traceback.print_exc()
        update_metadata(job_id, status=JobStatus.failed, error=message)
        append_run_log(job_id, "low", "Job failed", error=message)


pipeline_service = PipelineService()
