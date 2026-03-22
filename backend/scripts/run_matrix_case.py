import argparse
import json
import shutil
import time
from pathlib import Path

import httpx


def poll_job(client: httpx.Client, api_base: str, job_id: str, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = client.get(f"{api_base}/api/jobs/{job_id}?view=workbench", timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status in {"waiting_for_selection", "completed", "failed"}:
            return payload
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def copy_artifacts(payload: dict, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = Path(payload.get("output_dir") or "")
    if not root.exists():
        return
    copy_names = [
        "candidate_2.png",
        "05_generation_refined_candidate_2.png",
        "06_cleanup_binary.png",
        "07_cleanup_preview.png",
        "08_vector_final.svg",
        "09_vector_final_preview.png",
        "run.log",
        "metadata.json",
    ]
    for name in copy_names:
        src = root / name
        if src.exists():
            shutil.copy2(src, destination / name)


def run_case(args: argparse.Namespace) -> dict:
    source_image = Path(args.source_image)
    if not source_image.exists():
        raise FileNotFoundError(f"source image missing: {source_image}")

    out_root = Path(args.output_root)
    out_root.mkdir(parents=True, exist_ok=True)

    attempts = 0
    last_payload: dict | None = None
    with httpx.Client(timeout=180) as client:
        while attempts < args.retries:
            attempts += 1
            files = {"file": ("family.jpg", source_image.read_bytes(), "image/jpeg")}
            data = {
                "detail_level": "medium",
                "cleanup_strength": "medium",
                "num_variants": str(args.num_variants),
                "log_verbosity": "mid",
                "fabrication_style": "bold_signage",
                "prompt_profile": args.prompt_profile,
                "selection_mode": "manual",
                "benchmark_tag": args.slug,
                "source_image_id": "family.jpg",
                "inking_denoise": "0.5",
                "potrace_turdsize": "200",
                "potrace_opttolerance": "1.2",
                "cleanup_threshold_bias": str(args.cleanup_threshold_bias),
                "cleanup_min_component_px": str(args.cleanup_min_component_px),
                "cleanup_speck_morph": str(args.cleanup_speck_morph),
                "source_frontend": "workbench",
            }
            create = client.post(f"{args.api_base}/api/jobs", files=files, data=data, timeout=60)
            create.raise_for_status()
            job_id = create.json()["job_id"]
            print(f"[{args.slug}] started job_id={job_id} attempt={attempts}", flush=True)

            payload = poll_job(client, args.api_base, job_id, args.timeout_sec)
            if payload.get("status") == "waiting_for_selection":
                sel = client.post(
                    f"{args.api_base}/api/jobs/{job_id}/select-variant",
                    json={"candidate": "candidate_2.png"},
                    timeout=30,
                )
                sel.raise_for_status()
                payload = poll_job(client, args.api_base, job_id, args.timeout_sec)

            last_payload = payload
            status = payload.get("status")
            print(f"[{args.slug}] finished status={status} job_id={job_id}", flush=True)
            dest = out_root / f"{args.slug}__{job_id}"
            copy_artifacts(payload, dest)
            if status == "completed":
                return {
                    "slug": args.slug,
                    "job_id": job_id,
                    "status": status,
                    "folder": str(dest),
                    "error": payload.get("error"),
                    "cnc_metrics": payload.get("cnc_metrics", {}),
                    "quality_diagnostics": payload.get("quality_diagnostics", {}),
                }
            print(f"[{args.slug}] retrying due to status={status}", flush=True)

    assert last_payload is not None
    job_id = last_payload.get("job_id")
    dest = out_root / f"{args.slug}__{job_id}"
    return {
        "slug": args.slug,
        "job_id": job_id,
        "status": last_payload.get("status"),
        "folder": str(dest),
        "error": last_payload.get("error"),
        "cnc_metrics": last_payload.get("cnc_metrics", {}),
        "quality_diagnostics": last_payload.get("quality_diagnostics", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--source-image", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--prompt-profile", required=True)
    parser.add_argument("--cleanup-threshold-bias", type=int, default=0)
    parser.add_argument("--cleanup-min-component-px", type=int, default=40)
    parser.add_argument("--cleanup-speck-morph", type=int, default=0)
    parser.add_argument("--num-variants", type=int, default=4)
    parser.add_argument("--timeout-sec", type=int, default=2400)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    result = run_case(args)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
