import time
import traceback
from pathlib import Path
from threading import Thread

from app.config import settings as app_settings
from app.models import JobSettings, JobStatus
from app.services.image_ops import cleanup_raster, normalize_upload, preprocess
from app.services.siliconflow import FORCED_MODEL, NEGATIVE_PROMPT, PROMPT, generate_candidates, refine_candidate_with_inking
from app.services.storage import (
    append_run_log,
    job_dir,
    read_metadata,
    update_artifacts,
    update_metadata,
    update_stage_duration,
)
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
            )

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="ingestion")
            original_path, normalized_path = self._stage_ingest(job_id, upload_bytes)
            update_stage_duration(job_id, "ingestion", time.perf_counter() - start)
            update_artifacts(job_id, original=str(original_path), normalized=str(normalized_path))
            append_run_log(job_id, "mid", "Stage done", stage="ingestion", original=original_path.name, normalized=normalized_path.name)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="preprocessing")
            grayscale_path, edge_map_path = self._stage_preprocess(job_id, job_settings)
            update_stage_duration(job_id, "preprocessing", time.perf_counter() - start)
            update_artifacts(job_id, grayscale=str(grayscale_path), edge_map=str(edge_map_path))
            append_run_log(job_id, "mid", "Stage done", stage="preprocessing", grayscale=grayscale_path.name, edge_map=edge_map_path.name)

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
            append_run_log(
                job_id,
                "high",
                "Generation request prompts",
                prompt=PROMPT,
                negative_prompt=NEGATIVE_PROMPT,
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
            )
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

            if job_settings.num_variants > 1:
                update_metadata(job_id, status=JobStatus.waiting_for_selection, selected_candidate=None)
                append_run_log(job_id, "low", "Paused for user selection")
                return

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
            append_run_log(job_id, "mid", "Finalize pipeline", selected_candidate=candidate_name)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="inking")
            try:
                refined_path, inking_trace = self._stage_inking(job_id, candidate_path)
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
            update_artifacts(job_id, refined=str(refined_path))
            append_run_log(
                job_id,
                "mid",
                "Inking provider call",
                provider=inking_trace.get("provider"),
                configured_model=inking_trace.get("configured_model"),
                resolved_model=inking_trace.get("resolved_model"),
                denoising_strength=inking_trace.get("denoising_strength"),
                controlnet_model=inking_trace.get("controlnet_model"),
                provider_call_ms=inking_trace.get("provider_call_ms"),
                total_inking_ms=inking_trace.get("total_inking_ms"),
            )
            append_run_log(job_id, "mid", "Stage done", stage="inking", refined=refined_path.name)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="cleanup")
            binary_path, preview_path = self._stage_cleanup(job_id, refined_path, settings)
            update_stage_duration(job_id, "cleanup", time.perf_counter() - start)
            update_artifacts(job_id, binary=str(binary_path), cleanup_preview=str(preview_path))
            append_run_log(job_id, "mid", "Stage done", stage="cleanup", binary=binary_path.name, preview=preview_path.name)

            start = time.perf_counter()
            append_run_log(job_id, "low", "Stage start", stage="vectorization")
            svg_path, preview_svg_path = self._stage_vectorize(job_id, binary_path)
            update_stage_duration(job_id, "vectorization", time.perf_counter() - start)
            update_artifacts(job_id, final_svg=str(svg_path), final_preview=str(preview_svg_path))
            append_run_log(job_id, "mid", "Stage done", stage="vectorization", svg=svg_path.name, preview=preview_svg_path.name)

            update_metadata(job_id, status=JobStatus.completed, error=None)
            append_run_log(job_id, "low", "Job completed successfully")
        except Exception as exc:  # noqa: BLE001
            self._set_failed(job_id, exc)

    def _stage_ingest(self, job_id: str, upload_bytes: bytes) -> tuple[Path, Path]:
        root = job_dir(job_id)
        original = root / "01_input_original.png"
        normalized = root / "02_input_normalized.png"

        original.write_bytes(upload_bytes)
        normalize_upload(original, normalized)
        return original, normalized

    def _stage_preprocess(self, job_id: str, settings: JobSettings) -> tuple[Path, Path]:
        root = job_dir(job_id)
        normalized = root / "02_input_normalized.png"
        grayscale = root / "03_preprocess_grayscale.png"
        edge_map = root / "04_preprocess_edge_map.png"
        subject_mask = root / "05_preprocess_subject_mask.png"
        preprocess(normalized, grayscale, edge_map, settings.detail_level.value, subject_mask)
        return grayscale, edge_map

    def _stage_generate(self, job_id: str, settings: JobSettings) -> tuple[list[Path], dict]:
        root = job_dir(job_id)
        normalized = root / "02_input_normalized.png"
        generation_dir = root
        return generate_candidates(
            normalized,
            generation_dir,
            detail_level=settings.detail_level.value,
            num_variants=settings.num_variants,
        )

    def _stage_inking(self, job_id: str, candidate_path: Path) -> tuple[Path, dict]:
        root = job_dir(job_id)
        subject_mask = root / "05_preprocess_subject_mask.png"
        refined = root / "05_generation_refined.png"
        trace = refine_candidate_with_inking(candidate_path, subject_mask, refined)
        return refined, trace

    def _stage_cleanup(self, job_id: str, candidate_path: Path, settings: JobSettings) -> tuple[Path, Path]:
        root = job_dir(job_id)
        binary = root / "06_cleanup_binary.png"
        preview = root / "07_cleanup_preview.png"
        subject_mask = root / "05_preprocess_subject_mask.png"
        cleanup_raster(candidate_path, binary, preview, settings.cleanup_strength, subject_mask)
        return binary, preview

    def _stage_vectorize(self, job_id: str, binary_path: Path) -> tuple[Path, Path]:
        root = job_dir(job_id)
        svg_out = root / "08_vector_final.svg"
        preview_out = root / "09_vector_final_preview.png"
        vectorize(binary_path, svg_out, preview_out)
        return svg_out, preview_out

    def _set_failed(self, job_id: str, exc: Exception) -> None:
        message = f"{exc.__class__.__name__}: {exc}"
        traceback.print_exc()
        update_metadata(job_id, status=JobStatus.failed, error=message)
        append_run_log(job_id, "low", "Job failed", error=message)


pipeline_service = PipelineService()
