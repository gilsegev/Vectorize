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


class PromptProfile(str, Enum):
    legacy = "legacy"
    base_professional_pen = "base_professional_pen"
    stronger_polish = "stronger_polish"
    realism_preserving = "realism_preserving"
    balanced_default = "balanced_default"
    balanced_fallback_base_control = "balanced_fallback_base_control"
    realistic_seed = "realistic_seed"
    stylized_seed_do_not_default = "stylized_seed_do_not_default"
    variant_a_preserve_likeness = "variant_a_preserve_likeness"
    variant_b_selective_simplification = "variant_b_selective_simplification"
    variant_c_realism_leaning = "variant_c_realism_leaning"


class SelectionMode(str, Enum):
    manual = "manual"
    auto = "auto"


class SourceFrontend(str, Enum):
    storefront = "storefront"
    workbench = "workbench"


class JobSettings(BaseModel):
    detail_level: DetailLevel = DetailLevel.medium
    num_variants: int = Field(default=1, ge=1, le=4)
    cleanup_strength: CleanupStrength = CleanupStrength.medium
    log_verbosity: LogVerbosity = LogVerbosity.mid
    fabrication_style: FabricationStyle = FabricationStyle.bold_signage
    prompt_profile: PromptProfile = PromptProfile.balanced_default
    selection_mode: SelectionMode = SelectionMode.manual
    benchmark_tag: str | None = None
    source_image_id: str | None = None
    inking_denoise: float = Field(default=0.5, ge=0.1, le=0.9)
    potrace_turdsize: int = Field(default=200, ge=1, le=10000)
    potrace_opttolerance: float = Field(default=1.2, ge=0.1, le=5.0)
    cleanup_threshold_bias: int = Field(default=0, ge=-32, le=32)
    cleanup_min_component_px: int = Field(default=40, ge=8, le=5000)
    cleanup_speck_morph: int = Field(default=0, ge=0, le=2)


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
    prompt_version: str | None = None
    selection_reason: str | None = None
    candidate_scores: dict[str, Any] = Field(default_factory=dict)
    quality_diagnostics: dict[str, float | int | None] = Field(default_factory=dict)
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
    prompt_version: str | None = None
    selection_reason: str | None = None
    candidate_scores: dict[str, Any] = Field(default_factory=dict)
    quality_diagnostics: dict[str, float | int | None] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
