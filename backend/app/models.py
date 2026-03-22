from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    processing = "processing"
    waiting_for_selection = "waiting_for_selection"
    completed = "completed"
    failed = "failed"


class DetailLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class CleanupStrength(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class LogVerbosity(str, Enum):
    low = "low"
    mid = "mid"
    high = "high"


class JobSettings(BaseModel):
    detail_level: DetailLevel = DetailLevel.medium
    num_variants: int = Field(default=1, ge=1, le=4)
    cleanup_strength: CleanupStrength = CleanupStrength.medium
    log_verbosity: LogVerbosity = LogVerbosity.mid


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class ArtifactMap(BaseModel):
    original: str | None = None
    normalized: str | None = None
    grayscale: str | None = None
    edge_map: str | None = None
    refined: str | None = None
    binary: str | None = None
    cleanup_preview: str | None = None
    final_svg: str | None = None
    final_preview: str | None = None
    candidates: list[str] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    batch_run_id: str | None = None
    output_dir: str | None = None
    artifacts: ArtifactMap
    settings: JobSettings
    selected_candidate: str | None = None
    stage_durations: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    log_url: str | None = None


class SelectVariantRequest(BaseModel):
    candidate: str

    @field_validator("candidate")
    @classmethod
    def validate_candidate(cls, value: str) -> str:
        if not value.startswith("candidate_") or not value.endswith(".png"):
            raise ValueError("candidate must match candidate_<n>.png")
        return value


class Metadata(BaseModel):
    job_id: str
    batch_run_id: str | None = None
    status: JobStatus
    created_at: str
    settings: JobSettings
    selected_candidate: str | None = None
    stage_durations: dict[str, float] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
