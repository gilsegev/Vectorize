# Simplified Low-Level Design and Implementation Spec: Image to Vector App

## Goal

Build a simple internal app that:

* accepts an image upload
* generates a clean black-and-white line-art version using Stable Diffusion via SiliconFlow
* converts that result to SVG
* lets the user see the intermediate outputs
* lets the user download the final SVG

This version intentionally avoids overengineering. It is designed for a small app, low traffic, and fast implementation.

---

# 1. Product Scope

## In scope

* Single web app
* Upload one image at a time
* Run the pipeline end to end
* Show the outputs of each step
* Allow a few tunable settings
* Download final SVG and PNG preview

## Out of scope

* Complex observability stack
* Job queues and distributed workers
* Multi-user workflows
* Batch processing
* Benchmarking system
* Advanced analytics
* Fine-grained retries by phase
* Versioned presets in a database

---

# 2. Simplified Architecture

Use a basic 3-part architecture:

## Frontend

* Next.js
* Simple upload form
* Progress/status display
* Result page with phase previews

## Backend

* FastAPI
* Handles upload, pipeline execution, and result retrieval
* Runs the pipeline in-process for v1

## Storage

* Local disk storage for development and small internal usage
* SQLite for metadata if needed, or even just filesystem-based job folders for v1

If needed later, local disk can be swapped for S3 and SQLite for Postgres.

---

# 3. Simplified User Flow

1. User uploads image
2. User selects a style preset or leaves defaults
3. Backend runs:

   * normalization
   * preprocessing
   * generation through SiliconFlow
   * cleanup
   * vectorization
4. UI shows:

   * original image
   * preprocessed image or edge map
   * generated line-art candidates
   * cleaned binary raster
   * final SVG preview
5. User downloads final SVG

Optional:

* let user choose 1 of 2 to 4 generated variants before vectorization

---

# 4. Minimal Pipeline

## Step 1: Ingestion

Purpose:

* validate upload
* normalize orientation
* resize to a workable resolution

Implementation:

* use Pillow
* accept PNG, JPG, WEBP
* convert to PNG internally
* resize large images to max dimension, e.g. 1024 or 1536

Outputs:

* `original.png`
* `normalized.png`

---

## Step 2: Preprocessing

Purpose:

* make the image easier for generation and cleanup

Implementation:

* grayscale copy
* optional denoise
* optional contrast boost
* optional edge map using OpenCV Canny

Outputs:

* `grayscale.png`
* `edge_map.png`

Note:
For v1, this can stay very basic. It is mostly there to improve results and help the user understand what happened.

---

## Step 3: Generation with SiliconFlow

Purpose:

* transform the image into black-and-white line art

Implementation:

* use SiliconFlow Stable Diffusion image-to-image
* send normalized image
* use one prompt and one negative prompt
* request 2 to 4 variants max

Suggested prompt:
`monochrome vector-style line art, clean contours, strong silhouette, simplified shading, crisp black and white illustration`

Suggested negative prompt:
`blurry lines, messy background, painterly texture, gray wash, photoreal shading, noisy details`

Outputs:

* `candidate_1.png`
* `candidate_2.png`
* etc.

For v1:

* do not build a complex prompt management system
* keep prompts in a config file or constants module

---

## Step 4: Cleanup

Purpose:

* convert the selected candidate into a cleaner binary image before tracing

Implementation:

* grayscale
* threshold to black/white
* remove tiny noise blobs
* optional morphological open/close with OpenCV

Outputs:

* `binary.png`
* `cleanup_preview.png`

This step matters because Stable Diffusion output may look good visually but still trace badly.

---

## Step 5: Vectorization

Purpose:

* convert cleaned raster into SVG

Implementation:

* use Potrace or a wrapper around it
* generate SVG
* render SVG back to PNG for preview if needed

Outputs:

* `final.svg`
* `final_preview.png`

---

# 5. Simplified Backend Design

## Main modules

### `main.py`

Starts FastAPI app and registers routes.

### `routes/jobs.py`

Endpoints for:

* upload image and create job
* get job status
* get job results
* select variant if using manual selection

### `services/pipeline.py`

Main orchestration function that runs the steps in order.

### `services/siliconflow.py`

Wrapper for SiliconFlow API call.

### `services/image_ops.py`

Helpers for:

* normalization
* preprocessing
* cleanup

### `services/vectorize.py`

Wrapper for Potrace and preview rendering.

### `models.py`

Very light metadata model if using SQLite.

---

# 6. Simplified Data Model

A full relational model is not required for v1.

## Option A: simplest approach

Use one job folder per run:

```text
jobs/
  {job_id}/
    input/
      original.png
      normalized.png
    preprocessing/
      grayscale.png
      edge_map.png
    generation/
      candidate_1.png
      candidate_2.png
    cleanup/
      binary.png
      cleanup_preview.png
    vector/
      final.svg
      final_preview.png
    metadata.json
```

`metadata.json` can store:

* job id
* status
* created time
* settings used
* selected candidate
* file paths
* error if any

This is probably enough for the first build.

## Option B: slightly more structured

Use SQLite with a small `jobs` table and store file paths there.

For a simple internal app, Option A is totally reasonable.

---

# 7. API Spec

## `POST /api/jobs`

Upload a file and start processing.

Request:

* multipart form-data
* `file`
* optional settings

Response:

```json
{
  "job_id": "abc123",
  "status": "processing"
}
```

## `GET /api/jobs/{job_id}`

Return current status and available outputs.

Response:

```json
{
  "job_id": "abc123",
  "status": "waiting_for_selection",
  "artifacts": {
    "original": "/files/...",
    "normalized": "/files/...",
    "edge_map": "/files/...",
    "candidates": ["/files/...", "/files/..."]
  }
}
```

## `POST /api/jobs/{job_id}/select-variant`

Only needed if the user manually picks one candidate.

Request:

```json
{
  "candidate": "candidate_2.png"
}
```

Response:

```json
{
  "status": "processing"
}
```

## `GET /api/jobs/{job_id}/download/svg`

Download final SVG.

---

# 8. Execution Model

For simplicity, use one of these two approaches:

## Option 1: background thread

* request creates job
* backend starts background task
* UI polls for status

## Option 2: simple async task runner

* FastAPI background tasks or a lightweight queue

Recommendation:
Use a lightweight background task approach first. No Celery, no Redis unless you already have them.

For this app, Celery + Redis is likely unnecessary at the start.

---

# 9. Frontend Spec

## Pages

### `/`

Upload page.

Components:

* file uploader
* optional settings panel
* submit button

### `/jobs/[id]`

Result page.

Components:

* status badge
* original image
* preprocessing preview
* generation gallery
* selected candidate
* cleanup preview
* final SVG preview
* download button

## Minimal UI behavior

* poll every 2 to 3 seconds while processing
* if variants are generated, show them in a simple grid
* if manual selection is enabled, allow clicking one and continuing
* once final SVG exists, enable download

---

# 10. Minimal Settings

Keep settings very small in v1.

Suggested exposed controls:

* detail level: low / medium / high
* number of variants: 1 to 4
* cleanup strength: low / medium / high

Map these internally to real parameters.

Do not expose every SD and Potrace knob in the first version.

---

# 11. Config Example

```yaml
app:
  jobs_dir: ./jobs
  max_upload_mb: 20
  max_dimension: 1536

generation:
  model: stabilityai/stable-diffusion-xl-base-1.0
  steps: 30
  cfg_scale: 7.5
  strength: 0.55
  num_variants: 3
  prompt: "monochrome vector-style line art, clean contours, strong silhouette, simplified shading, crisp black and white illustration"
  negative_prompt: "blurry lines, messy background, painterly texture, gray wash, photoreal shading, noisy details"

cleanup:
  threshold_mode: adaptive
  min_component_area: 24
  morph_open_kernel: 2
  morph_close_kernel: 2

vectorization:
  turdsize: 8
  opttolerance: 0.2
```

---

# 12. Minimal Observability

Yes, the earlier version was too heavy for this goal.

For this app, observability should be simple:

## Keep

* basic logging
* per-job status
* elapsed time per stage
* error message if a step fails

## Skip for now

* OpenTelemetry
* Prometheus
* Grafana
* Sentry
* trace spans
* cost dashboards
* lineage systems

## Practical approach

Store in `metadata.json`:

* current status
* stage durations
* settings used
* selected candidate
* error field

That gives enough visibility for a small internal tool.

---

# 13. Error Handling

Each job should have a clear status:

* `processing`
* `waiting_for_selection`
* `completed`
* `failed`

If a step fails:

* stop the pipeline
* write the error into `metadata.json`
* show it in the UI

Do not build complex retry orchestration in v1.
A simple rerun button for the whole job is enough.

---

# 14. Implementation Plan

## Phase 1

Build end-to-end happy path:

* upload image
* normalize
* call SiliconFlow for 1 candidate
* cleanup
* vectorize
* show outputs
* download SVG

## Phase 2

Add usability:

* generate 2 to 4 candidates
* variant selection UI
* a few simple settings
* better previews

## Phase 3

Add polish only if needed:

* SQLite metadata instead of flat JSON
* background removal option
* rerun individual steps
* S3 storage if local disk becomes limiting

---

# 15. What the Coding Agent Should Build First

Priority order:

1. FastAPI backend with upload endpoint
2. Job folder creation and `metadata.json`
3. Image normalization with Pillow
4. SiliconFlow image-to-image wrapper
5. Cleanup with OpenCV
6. SVG tracing with Potrace
7. Next.js upload page and results page
8. Polling UI for job status
9. Download final SVG

Do not start with:

* complex DB schema
* distributed worker system
* full observability platform
* advanced preset/version management

---

# 16. Final Recommendation

For the app you described, the right mental model is:

**a small pipeline app with a clean UI**

not

**a production ML platform**

The simplest useful system is:

* Next.js frontend
* FastAPI backend
* local job folders
* SiliconFlow for generation
* OpenCV + Potrace for cleanup and vectorization
* simple logs and status files

That is enough to get a real product working quickly without unnecessary infrastructure.
