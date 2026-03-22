import argparse
import json
import time
from pathlib import Path

import httpx

REQUIRED_SUBJECTS = {
    "pet": "pet.jpg",
    "vehicle": "vehicle.jpg",
    "building": "building.jpg",
    "product": "product.jpg",
    "logo": "logo.png",
}
PROFILES = ["realistic_seed", "balanced_default", "stylized_seed_do_not_default"]


def poll_job(client: httpx.Client, api_base: str, job_id: str, timeout_sec: int = 1800) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        payload = client.get(f"{api_base}/api/jobs/{job_id}?view=workbench", timeout=30).json()
        if payload.get("status") in {"completed", "failed", "waiting_for_selection"}:
            return payload
        time.sleep(2)
    raise TimeoutError(job_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--input-dir", default="public/validation_inputs")
    parser.add_argument("--out", default="docs/validation_report.json")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    report: list[dict] = []
    with httpx.Client(timeout=180) as client:
        for subject, filename in REQUIRED_SUBJECTS.items():
            image = input_dir / filename
            if not image.exists():
                report.append({"subject": subject, "status": "missing_input", "expected_file": str(image)})
                continue
            image_bytes = image.read_bytes()
            mime = "image/png" if image.suffix.lower() == ".png" else "image/jpeg"
            for profile in PROFILES:
                data = {
                    "detail_level": "medium",
                    "cleanup_strength": "medium",
                    "num_variants": "1",
                    "log_verbosity": "mid",
                    "fabrication_style": "bold_signage",
                    "prompt_profile": profile,
                    "selection_mode": "manual",
                    "benchmark_tag": f"validation-{subject}-{profile}",
                    "source_image_id": filename,
                    "source_frontend": "workbench",
                }
                files = {"file": (filename, image_bytes, mime)}
                create = client.post(f"{args.api_base}/api/jobs", data=data, files=files, timeout=60)
                if create.status_code >= 400:
                    report.append(
                        {
                            "subject": subject,
                            "profile": profile,
                            "status": "create_failed",
                            "error": create.text,
                        }
                    )
                    continue
                job_id = create.json()["job_id"]
                payload = poll_job(client, args.api_base, job_id)
                report.append(
                    {
                        "subject": subject,
                        "profile": profile,
                        "job_id": job_id,
                        "status": payload.get("status"),
                        "output_dir": payload.get("output_dir"),
                        "error": payload.get("error"),
                        "cnc_metrics": payload.get("cnc_metrics", {}),
                    }
                )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote validation report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
