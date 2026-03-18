import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import ArtifactMap, JobSettings, JobStatus, JobStatusResponse, Metadata

_lock_by_job: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()
_batch_run_id = settings.batch_run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
_verbosity_order = {"low": 0, "mid": 1, "high": 2}
_legacy_jobs_dirs = ["../frontend/public/assets", "../frontend/public/Assets", "../public/assets"]


STAGE_DIRS = {
    "root": "",
}


def jobs_base_root() -> Path:
    configured = Path(settings.jobs_dir)
    if configured.is_absolute():
        base = configured
    else:
        # Resolve relative jobs_dir from backend directory, not process cwd.
        base = (Path(__file__).resolve().parents[2] / configured).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def _legacy_base_roots() -> list[Path]:
    roots: list[Path] = []
    for rel in _legacy_jobs_dirs:
        p = (Path(__file__).resolve().parents[2] / Path(rel)).resolve()
        if p.exists() and p != jobs_base_root():
            roots.append(p)
    return roots


def jobs_root() -> Path:
    root = jobs_base_root() / _batch_run_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_job_lock(job_id: str) -> threading.Lock:
    with _global_lock:
        lock = _lock_by_job.get(job_id)
        if lock is None:
            lock = threading.Lock()
            _lock_by_job[job_id] = lock
        return lock


def _find_existing_job_dir(job_id: str) -> Path | None:
    bases = [jobs_base_root(), *_legacy_base_roots()]
    for base in bases:
        # Current batch first for speed, then historical batch folders.
        current = base / _batch_run_id / job_id
        if current.exists():
            return current
        for batch_dir in base.iterdir():
            if not batch_dir.is_dir():
                continue
            candidate = batch_dir / job_id
            if candidate.exists():
                return candidate
    return None


def job_dir(job_id: str) -> Path:
    existing = _find_existing_job_dir(job_id)
    if existing is not None:
        return existing
    return jobs_root() / job_id


def ensure_job_structure(job_id: str) -> Path:
    root = job_dir(job_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_job(settings_payload: JobSettings) -> str:
    job_id = uuid.uuid4().hex[:12]
    ensure_job_structure(job_id)
    metadata = Metadata(
        job_id=job_id,
        batch_run_id=_batch_run_id,
        status=JobStatus.processing,
        created_at=datetime.now(timezone.utc).isoformat(),
        settings=settings_payload,
        artifacts={},
    )
    write_metadata(job_id, metadata.model_dump())
    return job_id


def metadata_path(job_id: str) -> Path:
    return job_dir(job_id) / "metadata.json"


def log_path(job_id: str) -> Path:
    return job_dir(job_id) / "run.log"


def write_metadata(job_id: str, payload: dict[str, Any]) -> None:
    path = metadata_path(job_id)
    with get_job_lock(job_id):
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_metadata(job_id: str) -> dict[str, Any]:
    path = metadata_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Unknown job {job_id}")
    with get_job_lock(job_id):
        return json.loads(path.read_text(encoding="utf-8"))


def update_metadata(job_id: str, **updates: Any) -> dict[str, Any]:
    metadata = read_metadata(job_id)
    metadata.update(updates)
    write_metadata(job_id, metadata)
    return metadata


def update_stage_duration(job_id: str, stage: str, duration_sec: float) -> None:
    metadata = read_metadata(job_id)
    durations = dict(metadata.get("stage_durations", {}))
    durations[stage] = round(duration_sec, 4)
    metadata["stage_durations"] = durations
    write_metadata(job_id, metadata)


def update_artifacts(job_id: str, **entries: Any) -> None:
    metadata = read_metadata(job_id)
    artifacts = dict(metadata.get("artifacts", {}))
    artifacts.update(entries)
    metadata["artifacts"] = artifacts
    write_metadata(job_id, metadata)


def append_run_log(job_id: str, level: str, message: str, **fields: Any) -> None:
    metadata = read_metadata(job_id)
    configured_level = (
        metadata.get("settings", {}).get("log_verbosity", "mid")
        if isinstance(metadata.get("settings"), dict)
        else "mid"
    )
    if _verbosity_order.get(level, 1) > _verbosity_order.get(configured_level, 1):
        return

    now = datetime.now(timezone.utc).isoformat()
    field_str = " ".join([f"{k}={v}" for k, v in fields.items()]) if fields else ""
    line = f"{now} [{level.upper()}] {message}"
    if field_str:
        line = f"{line} | {field_str}"

    path = log_path(job_id)
    with get_job_lock(job_id):
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def build_status_response(job_id: str) -> JobStatusResponse:
    data = read_metadata(job_id)
    resolved_dir = str(job_dir(job_id))
    artifacts = data.get("artifacts", {})
    artifact_map = ArtifactMap(
        original=artifacts.get("original"),
        normalized=artifacts.get("normalized"),
        grayscale=artifacts.get("grayscale"),
        edge_map=artifacts.get("edge_map"),
        binary=artifacts.get("binary"),
        cleanup_preview=artifacts.get("cleanup_preview"),
        final_svg=artifacts.get("final_svg"),
        final_preview=artifacts.get("final_preview"),
        candidates=artifacts.get("candidates", []),
    )
    return JobStatusResponse(
        job_id=job_id,
        status=data["status"],
        batch_run_id=data.get("batch_run_id"),
        output_dir=resolved_dir,
        artifacts=artifact_map,
        settings=JobSettings(**data.get("settings", {})),
        selected_candidate=data.get("selected_candidate"),
        stage_durations=data.get("stage_durations", {}),
        error=data.get("error"),
        log_url=f"/api/jobs/{job_id}/log",
    )
