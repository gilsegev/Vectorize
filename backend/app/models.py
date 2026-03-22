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


class FabricationStyle(str, Enum):
    precision_inlay = "precision_inlay"
    bold_signage = "bold_signage"
    abstract_art = "abstract_art"


class SourceFrontend(str, Enum):
    storefront = "storefront"
    workbench = "workbench"


class JobSettings(BaseModel):
    detail_level: DetailLevel = DetailLevel.medium
    num_variants: int = Field(default=1, ge=1, le=4)
    cleanup_strength: CleanupStrength = CleanupStrength.medium
    log_verbosity: LogVerbosity = LogVerbosity.mid
    fabrication_style: FabricationStyle = FabricationStyle.bold_signage
    inking_denoise: float = Field(default=0.5, ge=0.1, le=0.9)
    potrace_turdsize: int = Field(default=200, ge=1, le=10000)
    potrace_opttolerance: float = Field(default=1.2, ge=0.1, le=5.0)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class ArtifactMap(BaseModel):
    original: str | None = None
    normalized: str | None = None
    grayscale: str | None = None
    edge_map: str | None = None
    subject_mask: str | None = None
    refined: str | None = None
    refined_candidates: list[str] = Field(default_factory=list)
    binary: str | None = None
    cleanup_preview: str | None = None
    final_svg: str | None = None
    final_preview: str | None = None
    package_zip: str | None = None
    candidates: list[str] = Field(default_factory=list)


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    batch_run_id: str | None = None
    source_frontend: SourceFrontend = SourceFrontend.workbench
    output_dir: str | None = None
    artifacts: ArtifactMap
    settings: JobSettings
    selected_candidate: str | None = None
    stage_durations: dict[str, float] = Field(default_factory=dict)
    cnc_metrics: dict[str, float | int] = Field(default_factory=dict)
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


class RefineRerunRequest(BaseModel):
    inking_denoise: float = Field(ge=0.1, le=0.9)


class Metadata(BaseModel):
    job_id: str
    batch_run_id: str | None = None
    source_frontend: SourceFrontend = SourceFrontend.workbench
    status: JobStatus
    created_at: str
    settings: JobSettings
    selected_candidate: str | None = None
    stage_durations: dict[str, float] = Field(default_factory=dict)
    cnc_metrics: dict[str, float | int] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
