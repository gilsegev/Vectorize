# High-Level Design: AI-Assisted Image-to-Vector Line Art Pipeline

## Goal

Build a product that takes an input image and produces clean black-and-white vector-style line art, while exposing each intermediate phase in a UI and providing strong observability for debugging, quality tuning, and future automation.

This document is intended as implementation context for a coding agent. It describes the target system, the phased rollout, the major components, the end-to-end pipeline, and the operational concerns.

---

## Product Summary

The product ingests an image and transforms it through a staged pipeline:

1. Input ingestion and normalization
2. Image understanding and preprocessing
3. Line-art generation using Stable Diffusion via SiliconFlow
4. Raster cleanup and structural refinement
5. Raster-to-vector conversion
6. Result review, export, and iteration

The UI should let an operator:

* upload images
* choose or override processing settings
* run the pipeline phase by phase or end to end
* inspect outputs from every phase
* compare variants
* retry a phase with changed parameters
* export the final SVG and preview assets

The platform should also provide observability for:

* runtime and cost by phase
* prompt and model inputs/outputs
* quality metrics
* failures and retries
* artifact lineage from input to final export

---

## Core Principles

* Treat the system as a multi-stage production pipeline, not a single black-box model call.
* Persist artifacts at every phase so operators can inspect and replay work.
* Make each phase independently executable.
* Prefer asynchronous jobs and explicit job state transitions.
* Store full provenance for reproducibility.
* Design for phased delivery: useful manual tooling first, automation later.

---

## Target User Flows

### 1. Basic operator flow

1. User uploads image
2. User selects a preset such as `photo to line art`, `painting to engraving`, or `tactical photo to vector`
3. System runs all phases
4. UI shows intermediate outputs and final SVG
5. User adjusts settings and reruns selected phases if needed
6. User exports SVG, PNG preview, and metadata bundle

### 2. Advanced operator flow

1. User uploads image
2. User sets crop, threshold preferences, detail level, style prompt, and vector simplification strength
3. User runs each phase manually
4. User compares variants from the diffusion phase and vectorization phase
5. User approves one result as final

### 3. Internal tuning flow

1. Team reviews failed or low-quality runs
2. Team inspects traces, parameters, artifacts, and metrics
3. Team updates prompts, preprocessing settings, or conversion thresholds
4. Team reruns on a benchmark set

---

## System Overview

### Frontend

A web application for operators and reviewers.

Responsibilities:

* upload and manage jobs
* configure settings and presets
* display pipeline progress
* preview artifacts from every phase
* compare variants side by side
* surface logs, timings, and errors
* export outputs

Suggested views:

* Job list
* New job form
* Job detail with phase timeline
* Artifact gallery by phase
* Side-by-side compare view
* Admin / observability dashboard

### Backend API

A service exposing job, artifact, settings, and orchestration endpoints.

Responsibilities:

* accept uploads
* create and manage jobs
* schedule phase execution
* persist metadata
* expose artifact URLs and run history
* support retries and partial reruns

### Orchestrator / Worker System

Background workers run each phase of the pipeline.

Responsibilities:

* execute jobs asynchronously
* support per-phase retries
* update job state transitions
* emit structured logs, metrics, and traces

### Model Gateway

An internal wrapper around SiliconFlow Stable Diffusion inference.

Responsibilities:

* build prompts and request payloads
* call SiliconFlow APIs
* manage model versioning and request options
* normalize outputs into internal artifact format
* record cost and latency

### Artifact Store

Blob storage for original uploads and all intermediate/final artifacts.

Artifacts include:

* original upload
* normalized image
* background-removed image
* edge map / segmentation overlay
* diffusion outputs
* cleaned raster line art
* vector SVG
* preview PNG
* debug overlays

### Metadata Store

Relational database for jobs, phases, parameters, metrics, approvals, and lineage.

### Observability Stack

Tracing, metrics, structured logs, and quality dashboards.

---

## Phase-Based Product Delivery

## Phase 0: Manual prototype

Goal: validate the pipeline with minimal product surface.

Scope:

* single-image upload
* manual invocation of each pipeline step
* SiliconFlow-based line-art generation
* SVG export
* local or basic cloud storage for artifacts
* simple debug page showing per-step outputs

Success criteria:

* team can reliably produce acceptable outputs on a small benchmark set
* each phase output is persisted and visible
* failure modes are understood

Not yet included:

* user accounts
* multi-tenant controls
* automated scoring
* advanced analytics

---

## Phase 1: Internal tool

Goal: create a usable operator-facing product.

Scope:

* authenticated UI
* job queue and background workers
* preset-based execution
* per-phase rerun
* artifact timeline
* side-by-side comparison of variants
* structured logging and tracing
* basic metrics dashboard

Success criteria:

* operators can run jobs without engineering help
* failures are diagnosable via logs and artifacts
* the team can compare prompts and parameters across runs

---

## Phase 2: Production MVP

Goal: stable product with operational visibility and export readiness.

Scope:

* robust job orchestration
* retry policies and failure recovery
* role-based access
* benchmark set support
* quality scoring and approval workflow
* usage analytics and cost reporting
* configurable presets and versioning
* downloadable metadata bundle with provenance

Success criteria:

* predictable end-to-end execution
* acceptable latency and cost per job
* strong reproducibility
* quality can be monitored over time

---

## Phase 3: Optimization and automation

Goal: improve quality and reduce manual intervention.

Scope:

* automatic model/prompt selection by image type
* ranking among multiple diffusion variants
* automatic cleanup heuristics
* batch processing
* benchmark regression detection
* human feedback loop into prompt and parameter tuning

Success criteria:

* reduced reruns
* higher first-pass acceptance rate
* lower operator time per image

---

## End-to-End Pipeline

## Phase A: Ingestion and normalization

Input: user-uploaded image
Output: normalized working image

Responsibilities:

* accept JPG, PNG, WEBP
* validate dimensions and file size
* normalize orientation via EXIF
* convert to canonical format
* resize into one or more working resolutions
* generate thumbnail and preview
* assign job ID and artifact lineage

Suggested implementation:

* image processing library for normalization
* store original and normalized versions separately

Observability:

* input dimensions
* file size
* normalization time
* any auto-rotations or format conversions

UI:

* original image preview
* normalized image preview
* input metadata panel

---

## Phase B: Preprocessing and image understanding

Input: normalized image
Output: preprocessing artifacts used to guide line-art generation and cleanup

Responsibilities:

* optional background removal
* optional subject detection / foreground isolation
* optional contrast expansion
* optional denoising
* optional edge map generation
* optional segmentation or saliency mask
* optional crop suggestions

Purpose:
This phase improves consistency before diffusion and gives the operator visibility into what the system thinks matters.

Outputs may include:

* foreground mask
* edge map
* subject crop
* high-contrast grayscale version
* segmentation overlay

Observability:

* preprocessing settings used
* histogram stats
* foreground coverage ratio
* edge density metrics

UI:

* tabbed previews for every preprocessing artifact
* toggles to enable or disable preprocessing substeps
* controls for crop, threshold, and denoise strength

---

## Phase C: Line-art generation with SiliconFlow Stable Diffusion

Input: normalized image plus optional guidance artifacts
Output: one or more raster line-art candidates

Responsibilities:

* construct prompt and negative prompt
* select SiliconFlow model and version
* optionally use image-to-image flow
* optionally use control input such as edge map or conditioning image if supported by chosen setup
* request multiple candidate generations
* persist all outputs and model metadata

Why this exists:
This is the semantic transformation phase. Instead of merely tracing edges, the model reinterprets the image as clean black-and-white illustration.

Prompting strategy:

* describe target as monochrome vector-style line art
* emphasize clean contours, readable anatomy, simplified shading, strong silhouette
* discourage noise, gray wash, painterly texture, clutter, photoreal shading

Possible generation settings:

* seed
* guidance scale
* denoise strength
* number of steps
* output resolution
* number of variants
* style preset

SiliconFlow integration responsibilities:

* endpoint wrapper
* request signing or auth
* timeout and retry handling
* request/response normalization
* cost and latency recording

Observability:

* model name and version
* prompt and negative prompt version IDs
* latency per call
* token or image generation cost if available
* seed and generation parameters
* output count and success rate

UI:

* generated variant gallery
* compare mode for variants
* display prompt and settings used
* rerun generation with changed settings

---

## Phase D: Raster cleanup and structural refinement

Input: selected raster line-art candidate
Output: cleaned black-and-white raster suitable for vectorization

Responsibilities:

* binarization
* morphological cleanup
* remove specks and isolated noise
* bridge broken lines when possible
* simplify filled regions
* sharpen contour consistency
* optionally apply domain-specific cleanup rules for fur, feathers, armor, and face details

Purpose:
Stable Diffusion outputs may look good visually but still be poor inputs for vector conversion. This phase prepares them for path extraction.

Possible techniques:

* adaptive thresholding
* connected component filtering
* contour closing
* hole filling rules
* line thinning or thickening controls

Observability:

* connected component counts before and after cleanup
* black pixel ratio
* broken contour estimates
* cleanup runtime

UI:

* before/after raster cleanup compare slider
* controls for threshold, speck removal, line thickness, contour closure

---

## Phase E: Raster-to-vector conversion

Input: cleaned binary raster
Output: SVG and vector preview assets

Responsibilities:

* trace raster into vector paths
* fit curves and simplify paths
* detect and remove tiny unwanted shapes
* preserve important contours
* generate preview PNG from SVG
* store final SVG and path metadata

Possible implementation:

* Potrace-style tracing or equivalent vectorization engine
* configurable simplification tolerance
* minimum path area filter
* optional path smoothing and corner preservation

Key controls:

* path simplification strength
* corner sensitivity
* minimum region area
* stroke versus fill strategy

Observability:

* number of paths
* anchor point count
* SVG size
* simplification ratio
* runtime

UI:

* SVG preview pane
* overlay compare with cleaned raster
* sliders for simplification and smoothing
* rerun vectorization without redoing earlier phases

---

## Phase F: Review, export, and provenance

Input: vector output and upstream metadata
Output: downloadable final package and review record

Responsibilities:

* mark result accepted or rejected
* capture operator notes
* export SVG
* export PNG preview
* export provenance JSON containing prompts, settings, model versions, timings, and artifact references

Observability:

* acceptance rate
* rerun counts before approval
* export counts by preset and image category

UI:

* final review panel
* approval action
* export controls
* provenance view

---

## Data Model

### Job

Represents one end-to-end user request.

Fields:

* id
* status
* preset
* created_by
* created_at
* updated_at
* current_phase
* selected_variant_id
* final_artifact_id

### Phase Run

Represents execution of a single phase for a job.

Fields:

* id
* job_id
* phase_name
* status
* started_at
* completed_at
* input_artifact_ids
* output_artifact_ids
* parameter_snapshot
* error_message
* retry_count

### Artifact

Represents any stored intermediate or final asset.

Fields:

* id
* job_id
* phase_name
* artifact_type
* storage_uri
* mime_type
* width
* height
* metadata_json
* created_at

### Preset

Represents a named pipeline configuration.

Fields:

* id
* name
* description
* preprocessing_config
* generation_config
* cleanup_config
* vectorization_config
* version

### Review

Represents operator feedback and final decision.

Fields:

* id
* job_id
* reviewer
* status
* notes
* created_at

---

## API Surface

Suggested endpoints:

* `POST /jobs` create job with upload and preset
* `GET /jobs/:id` get job summary
* `GET /jobs/:id/artifacts` list artifacts by phase
* `POST /jobs/:id/run` run full pipeline
* `POST /jobs/:id/phases/:phase/run` run single phase
* `POST /jobs/:id/phases/:phase/retry` retry failed phase
* `POST /jobs/:id/select-variant` choose generation variant
* `POST /jobs/:id/review` approve or reject
* `GET /presets` list presets
* `POST /presets` create preset
* `GET /metrics/jobs` operational metrics
* `GET /metrics/quality` quality metrics

---

## Orchestration Model

Use a phase-driven state machine.

Example phase states:

* pending
* queued
* running
* succeeded
* failed
* skipped
* canceled

Job progression:

1. create job
2. run ingestion
3. run preprocessing
4. run generation
5. user or policy selects best generation variant
6. run cleanup
7. run vectorization
8. review and export

Support:

* full job execution
* partial rerun from any phase
* multiple candidate branches from generation onward

Important design choice:
Generation should allow branching. A single input image may produce several variants, and each chosen variant may continue through cleanup and vectorization separately.

---

## UI Design

## Main job detail layout

Suggested layout:

* left sidebar: phase timeline and job metadata
* center: artifact viewer for selected phase
* right panel: controls, parameters, logs, and metrics

### Core UI components

1. Upload panel
2. Preset selector
3. Phase timeline
4. Artifact tabs per phase
5. Variant gallery
6. Compare viewer
7. Parameter editor
8. Run / rerun controls
9. Logs and metrics drawer
10. Review and export panel

### Compare modes

Support:

* original vs normalized
* original vs edge map
* generated variant A vs B
* cleaned raster vs SVG overlay

### Operator affordances

* rerun from selected phase
* clone job with modified settings
* save settings as preset
* mark a phase output as preferred
* add notes to job or phase

---

## Observability Design

## Logging

Emit structured logs for every phase run.

Include:

* job_id
* phase_run_id
* phase_name
* preset_version
* parameter snapshot hash
* model version
* timing
* error class
* storage URIs for artifacts

## Metrics

Track at minimum:

* jobs created
* jobs completed
* jobs failed
* average latency by phase
* phase retry rate
* SiliconFlow latency and error rate
* average cost per job
* first-pass acceptance rate
* total reruns per approved job
* average SVG path count

## Tracing

Each job should have an end-to-end trace with spans for:

* upload
* normalization
* preprocessing substeps
* SiliconFlow request
* cleanup
* vectorization
* export

## Quality analytics

Track quality indicators over time:

* acceptance by preset
* acceptance by image category
* vector complexity distribution
* common failure types
* prompt version performance

## Artifact lineage

Every artifact should be traceable back to:

* source image
* phase that created it
* parameter snapshot
* upstream artifact IDs
* model version

This is critical for debugging and regression testing.

---

## Benchmarking and Evaluation

Create a small benchmark set early.

Include categories such as:

* portrait photos
* historical costumes / armor
* wildlife or fur-heavy subjects
* tactical or equipment-heavy subjects
* paintings / iconography / wings and feathers

For each benchmark item, record:

* expected qualities
* accepted output examples
* failure notes

Evaluation dimensions:

* silhouette readability
* facial clarity
* texture stylization quality
* background suppression
* vector cleanliness
* operator acceptance

This benchmark set will be used in Phase 2 and beyond to prevent regressions.

---

## Failure Modes and Mitigations

### 1. Model output too noisy

Mitigations:

* stronger negative prompts
* better preprocessing
* request more variants and rank them
* stricter cleanup thresholds

### 2. Lost important subject detail

Mitigations:

* increase resolution
* use different preset
* reduce simplification during cleanup or vectorization
* add crop and foreground isolation

### 3. Vector output too complex

Mitigations:

* stronger raster cleanup
* higher path simplification
* minimum region area filtering

### 4. Broken contours in final SVG

Mitigations:

* contour closure during cleanup
* tune binarization
* domain-specific line repair

### 5. High latency or cost from generation

Mitigations:

* reduce variants by default
* reuse preprocessing artifacts
* enable partial reruns only from generation onward
* add preset-specific defaults by image type

---

## Suggested Initial Tech Choices

These are suggestions, not requirements.

Frontend:

* React or Next.js
* image compare viewer
* job timeline UI

Backend:

* Python or TypeScript service
* REST API
* background queue for phase execution

Workers:

* containerized workers per phase
* separate generation worker for SiliconFlow calls

Storage:

* object storage for artifacts
* relational DB for metadata

Image processing:

* OpenCV or Pillow-class tooling for preprocessing and cleanup
* Potrace-style vectorization engine

Observability:

* OpenTelemetry for traces
* metrics backend for dashboards
* centralized structured logs

---

## Implementation Notes for Coding Agent

### Non-goals for first build

* fully automatic best-variant selection
* collaborative editing
* real-time multi-user workflows
* extremely advanced vector editing in browser

### Must-have behavior

* every phase can run independently
* every phase persists outputs
* users can inspect outputs from every phase
* users can rerun later phases without repeating the whole pipeline
* every output has provenance
* all SiliconFlow requests are logged with model/version/params metadata

### Recommended architecture pattern

Use a job-oriented pipeline with immutable artifacts and parameter snapshots. Avoid hidden in-memory state between phases. Treat each phase as a pure transformation from input artifacts + settings to output artifacts.

---

## Example Execution Sequence

1. User uploads source image
2. Backend creates job and stores original artifact
3. Ingestion worker normalizes image
4. Preprocessing worker generates mask, edge map, and debug previews
5. Generation worker calls SiliconFlow Stable Diffusion and stores multiple line-art variants
6. User selects preferred variant in UI
7. Cleanup worker binarizes and refines chosen raster
8. Vectorization worker creates SVG and preview PNG
9. User reviews all outputs and exports final package
10. System stores review decision and metrics

---

## Final Outcome

The final product is not just a model wrapper. It is an operator-facing system for controlled image transformation, where each step is visible, repeatable, and measurable.

The most important design decision is to separate:

* semantic generation
* cleanup
* vectorization
* review and export

That separation is what makes the system debuggable, tunable, and suitable for iterative product improvement.
