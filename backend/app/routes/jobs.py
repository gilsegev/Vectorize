from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.models import (
    CleanupStrength,
    DetailLevel,
    FabricationStyle,
    JobCreateResponse,
    JobSettings,
    JobStatus,
    LogVerbosity,
    PromptProfile,
    RefineRerunRequest,
    SelectionMode,
    SelectVariantRequest,
    StylePreset,
    SourceFrontend,
)
from app.services.pipeline import pipeline_service
from app.services.storage import build_status_response, create_job, job_dir, log_path, read_metadata, update_artifacts

router = APIRouter(prefix="/jobs", tags=["jobs"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FABRICATION_PRESETS: dict[FabricationStyle, tuple[float, int, float]] = {
    FabricationStyle.precision_inlay: (0.35, 80, 0.5),
    FabricationStyle.bold_signage: (0.50, 200, 1.2),
    FabricationStyle.abstract_art: (0.65, 400, 2.0),
}
STYLE_TO_PROMPT: dict[StylePreset, PromptProfile] = {
    StylePreset.legacy: PromptProfile.legacy,
    StylePreset.realistic: PromptProfile.realistic_seed,
    StylePreset.balanced: PromptProfile.balanced_default,
    StylePreset.stylized: PromptProfile.stylized_v3_bold_cartoon,
}


def _artifact_to_url(job_id: str, artifact: str | None, *, scope: str = "workbench") -> str | None:
    if not artifact:
        return None
    file_path = Path(artifact)
    root = job_dir(job_id)
    try:
        relative = file_path.resolve().relative_to(root.resolve())
        relative_part = str(relative).replace("\\", "/")
    except Exception:
        relative_part = file_path.name
    return f"/api/jobs/{job_id}/files/{relative_part}?scope={scope}"


@router.post("", response_model=JobCreateResponse)
async def create_job_endpoint(
    file: UploadFile = File(...),
    detail_level: DetailLevel = Form(DetailLevel.medium),
    num_variants: int = Form(1),
    cleanup_strength: CleanupStrength = Form(CleanupStrength.medium),
    log_verbosity: LogVerbosity = Form(LogVerbosity.mid),
    fabrication_style: FabricationStyle = Form(FabricationStyle.bold_signage),
    prompt_profile: PromptProfile = Form(PromptProfile.balanced_default),
    style_preset: StylePreset | None = Form(None),
    style_preset_alias: str | None = Form(None, alias="stylePreset"),
    selection_mode: SelectionMode = Form(SelectionMode.manual),
    benchmark_tag: str | None = Form(None),
    source_image_id: str | None = Form(None),
    inking_denoise: float | None = Form(None),
    potrace_turdsize: int | None = Form(None),
    potrace_opttolerance: float | None = Form(None),
    cleanup_threshold_bias: int = Form(0),
    cleanup_min_component_px: int = Form(20),
    cleanup_speck_morph: int = Form(0),
    source_frontend: SourceFrontend = Form(SourceFrontend.workbench),
) -> JobCreateResponse:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    contents = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if not contents:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    preset_denoise, preset_turdsize, preset_opttol = FABRICATION_PRESETS[fabrication_style]
    resolved_style_preset = style_preset
    if resolved_style_preset is None and style_preset_alias:
        try:
            resolved_style_preset = StylePreset(style_preset_alias)
        except Exception:
            resolved_style_preset = StylePreset.balanced
    if resolved_style_preset is None:
        resolved_style_preset = StylePreset.balanced
    if resolved_style_preset == StylePreset.stylized and not settings.enable_stylized_preset:
        resolved_style_preset = StylePreset.balanced

    resolved_prompt_profile = STYLE_TO_PROMPT.get(resolved_style_preset, PromptProfile.balanced_default)
    if prompt_profile != PromptProfile.balanced_default:
        # Workbench may set prompt_profile directly; keep explicit setting as highest priority.
        resolved_prompt_profile = prompt_profile

    effective_selection_mode = selection_mode
    if source_frontend == SourceFrontend.storefront:
        effective_selection_mode = SelectionMode.auto if settings.enable_auto_selection else SelectionMode.manual
    settings_payload = JobSettings(
        detail_level=detail_level,
        num_variants=num_variants,
        cleanup_strength=cleanup_strength,
        log_verbosity=log_verbosity,
        fabrication_style=fabrication_style,
        style_preset=resolved_style_preset,
        prompt_profile=resolved_prompt_profile,
        selection_mode=effective_selection_mode,
        benchmark_tag=benchmark_tag,
        source_image_id=source_image_id,
        inking_denoise=(inking_denoise if inking_denoise is not None else preset_denoise),
        potrace_turdsize=(potrace_turdsize if potrace_turdsize is not None else preset_turdsize),
        potrace_opttolerance=(potrace_opttolerance if potrace_opttolerance is not None else preset_opttol),
        cleanup_threshold_bias=cleanup_threshold_bias,
        cleanup_min_component_px=cleanup_min_component_px,
        cleanup_speck_morph=cleanup_speck_morph,
    )
    job_id = create_job(settings_payload, source_frontend=source_frontend)
    pipeline_service.start_job(job_id, contents, file.filename or "input")
    return JobCreateResponse(job_id=job_id, status=JobStatus.processing)


@router.get("/style-capabilities")
def style_capabilities() -> dict:
    available = [StylePreset.legacy.value, StylePreset.realistic.value, StylePreset.balanced.value]
    if settings.enable_stylized_preset:
        available.append(StylePreset.stylized.value)
    return {
        "availableStylePresets": available,
        "defaultStylePreset": StylePreset.balanced.value,
    }


@router.get("/{job_id}")
def get_job(job_id: str, view: str = "workbench") -> dict:
    try:
        response = build_status_response(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = response.model_dump()
    scope = "workbench" if view == "workbench" else "storefront"
    artifacts = payload["artifacts"]
    for key in [
        "original",
        "normalized",
        "grayscale",
        "edge_map",
        "subject_mask",
        "refined",
        "binary",
        "cleanup_preview",
        "final_svg",
        "final_preview",
        "package_zip",
    ]:
        artifacts[key] = _artifact_to_url(job_id, artifacts.get(key), scope=scope)
    artifacts["candidates"] = [_artifact_to_url(job_id, p, scope=scope) for p in artifacts.get("candidates", [])]
    artifacts["refined_candidates"] = [_artifact_to_url(job_id, p, scope=scope) for p in artifacts.get("refined_candidates", [])]

    if view == "storefront":
        return {
            "job_id": payload["job_id"],
            "status": payload["status"],
            "batch_run_id": payload.get("batch_run_id"),
            "source_frontend": payload.get("source_frontend"),
            "settings": {
                "fabrication_style": payload.get("settings", {}).get("fabrication_style"),
                "style_preset": payload.get("settings", {}).get("style_preset"),
            },
            "cnc_metrics": payload.get("cnc_metrics", {}),
            "artifacts": {
                "art": artifacts.get("final_preview"),
                "toolpath_svg": artifacts.get("final_svg"),
                "package_zip": artifacts.get("package_zip"),
            },
            "error": payload.get("error"),
        }
    return payload


@router.post("/{job_id}/select-variant")
def select_variant(job_id: str, request: SelectVariantRequest) -> dict[str, str]:
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if metadata["status"] != JobStatus.waiting_for_selection:
        raise HTTPException(status_code=409, detail="Job is not waiting for variant selection")

    candidates = metadata.get("artifacts", {}).get("candidates", [])
    names = {Path(path).name for path in candidates}
    if request.candidate not in names:
        raise HTTPException(status_code=400, detail="Candidate not found")

    pipeline_service.resume_with_selected_variant(job_id, request.candidate)
    return {"status": JobStatus.processing}


@router.get("/{job_id}/download/svg")
def download_svg(job_id: str):
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if metadata["status"] != JobStatus.completed:
        raise HTTPException(status_code=409, detail="Job is not completed")

    final_svg = metadata.get("artifacts", {}).get("final_svg")
    if not final_svg or not Path(final_svg).exists():
        raise HTTPException(status_code=404, detail="SVG not found")

    return FileResponse(final_svg, media_type="image/svg+xml", filename="final.svg")


@router.get("/{job_id}/download/package")
def download_package(job_id: str):
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if metadata["status"] != JobStatus.completed:
        raise HTTPException(status_code=409, detail="Job is not completed")

    artifacts = metadata.get("artifacts", {})
    package_zip = artifacts.get("package_zip")
    if not package_zip:
        root = job_dir(job_id)
        package_path = root / f"{job_id}_Package.zip"
        if package_path.exists():
            package_zip = str(package_path)
            update_artifacts(job_id, package_zip=package_zip)
    if not package_zip or not Path(package_zip).exists():
        raise HTTPException(status_code=404, detail="Package zip not found")
    return FileResponse(package_zip, media_type="application/zip", filename=f"{job_id}_Package.zip")


@router.get("/{job_id}/log")
def get_run_log(job_id: str):
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = log_path(job_id)
    if not path.exists():
        message = (
            "Run log not available for this job.\n"
            "This usually means the job was created before per-run logging was enabled.\n"
            f"status={metadata.get('status')} job_id={job_id}"
        )
        return PlainTextResponse(message, status_code=200)
    return FileResponse(str(path), media_type="text/plain", filename="run.log")


@router.post("/{job_id}/log/clear")
def clear_run_log(job_id: str):
    try:
        read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = log_path(job_id)
    path.write_text("", encoding="utf-8")
    return {"status": "cleared"}


@router.post("/{job_id}/open-output-dir")
def open_output_dir(job_id: str):
    try:
        read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    directory = job_dir(job_id)
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=404, detail="Output directory not found")
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(directory)])
        return {"status": "opened", "path": str(directory)}
    raise HTTPException(status_code=501, detail="Open directory is only implemented for Windows")


@router.get("/{job_id}/files/{artifact_path:path}")
def get_artifact_file(job_id: str, artifact_path: str, scope: str = "storefront"):
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if metadata.get("source_frontend") == SourceFrontend.storefront and scope != "workbench":
        allowed = {"09_vector_final_preview.png", "08_vector_final.svg", f"{job_id}_Package.zip"}
        if Path(artifact_path).name not in allowed:
            raise HTTPException(status_code=403, detail="Asset is restricted in storefront view")
    root = job_dir(job_id).resolve()
    file_path = (root / artifact_path).resolve()
    try:
        file_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@router.post("/{job_id}/refine-rerun")
def refine_rerun(job_id: str, request: RefineRerunRequest) -> dict[str, str]:
    try:
        metadata = read_metadata(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if metadata.get("status") not in [JobStatus.completed, JobStatus.failed]:
        raise HTTPException(status_code=409, detail="Job must be completed or failed before rerun")
    pipeline_service.refine_and_rerun(job_id, request.inking_denoise)
    return {"status": JobStatus.processing}
