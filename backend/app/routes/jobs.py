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
    JobCreateResponse,
    JobSettings,
    JobStatus,
    LogVerbosity,
    SelectVariantRequest,
)
from app.services.pipeline import pipeline_service
from app.services.storage import build_status_response, create_job, job_dir, log_path, read_metadata

router = APIRouter(prefix="/jobs", tags=["jobs"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _artifact_to_url(job_id: str, artifact: str | None) -> str | None:
    if not artifact:
        return None
    file_path = Path(artifact)
    root = job_dir(job_id)
    try:
        relative = file_path.resolve().relative_to(root.resolve())
        relative_part = str(relative).replace("\\", "/")
    except Exception:
        relative_part = file_path.name
    return f"/api/jobs/{job_id}/files/{relative_part}"


@router.post("", response_model=JobCreateResponse)
async def create_job_endpoint(
    file: UploadFile = File(...),
    detail_level: DetailLevel = Form(DetailLevel.medium),
    num_variants: int = Form(1),
    cleanup_strength: CleanupStrength = Form(CleanupStrength.medium),
    log_verbosity: LogVerbosity = Form(LogVerbosity.mid),
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

    settings_payload = JobSettings(
        detail_level=detail_level,
        num_variants=num_variants,
        cleanup_strength=cleanup_strength,
        log_verbosity=log_verbosity,
    )
    job_id = create_job(settings_payload)
    pipeline_service.start_job(job_id, contents, file.filename or "input")
    return JobCreateResponse(job_id=job_id, status=JobStatus.processing)


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        response = build_status_response(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = response.model_dump()
    artifacts = payload["artifacts"]
    for key in ["original", "normalized", "grayscale", "edge_map", "binary", "cleanup_preview", "final_svg", "final_preview"]:
        artifacts[key] = _artifact_to_url(job_id, artifacts.get(key))
    artifacts["candidates"] = [_artifact_to_url(job_id, p) for p in artifacts.get("candidates", [])]
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
def get_artifact_file(job_id: str, artifact_path: str):
    root = job_dir(job_id).resolve()
    file_path = (root / artifact_path).resolve()
    try:
        file_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))
