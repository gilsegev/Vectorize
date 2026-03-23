# Stylized Minimal Tuning Plan

## Goal
Tune the new stylized mode to recover the stronger cartoonification/polish look while keeping key subject detail.

## Scope
- Tune generation prompt profiles only in this round.
- Keep cleanup and vectorization fixed for experiment validity.
- Use a minimal control set to reduce runtime.

## Profiles Under Test
- `stylized_v1_detail_preserving`
- `stylized_v2_balanced_cartoon`
- `stylized_v3_bold_cartoon`
- `stylized_v4_graphic_poster`

Anchor controls (run only on anchor images):
- `legacy`
- `balanced_default`

## Minimal Experiment Design
- Full image set: run stylized profiles only.
- Anchor subset (2-3 images): run anchor controls plus stylized profiles.
- Suggested anchors:
  - `car.jpg`
  - `dog.jpg`

## Command
From repo root:

```powershell
d:\vecrorize\backend\.venv\Scripts\python.exe d:\vecrorize\backend\scripts\run_stylized_minimal_benchmark.py `
  --api-base http://127.0.0.1:8000 `
  --image-dir d:\vecrorize\public\benchmark `
  --images car.jpg dog.jpg portrait_1.jpg product.jpg `
  --anchor-images car.jpg dog.jpg `
  --benchmark-tag stylized-minimal-r1
```

## Outputs
- JSON report: `docs/stylized_minimal_last_run.json`
- CSV report: `docs/stylized_minimal_last_run.csv`
- Full job artifacts remain under `public/Assets/<batch>/<job_id>/`

## Promotion Gate (Round 1)
- Pass if one stylized profile:
  - is preferred over current stylized seed on most images by visual review,
  - does not regress anchor images versus `legacy` on key detail readability,
  - stays within CNC safety bounds (`node_count` not exploding beyond practical limits).

## Next Step After Round 1
- Promote winner to storefront `stylized` mapping.
- Keep current stylized seed as fallback profile for quick rollback.
