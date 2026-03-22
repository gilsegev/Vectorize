import argparse
import json
import mimetypes
import time
from pathlib import Path
from urllib import error, parse, request


DEFAULT_IMAGES = [
    "car.jpg",
    "portrait_1.jpg",
    "portrait_2.jpg",
    "dog.jpg",
]


def _post_multipart(url: str, fields: dict[str, str], file_path: Path) -> dict:
    boundary = "----VectorizeBenchBoundary123456789"
    body = bytearray()
    for key, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = request.Request(url, method="POST", data=bytes(body))
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_terminal(api_base: str, job_id: str, timeout_sec: float = 900.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        payload = _get_json(f"{api_base}/api/jobs/{job_id}?view=workbench")
        if payload.get("status") in {"completed", "failed", "waiting_for_selection"}:
            return payload
        time.sleep(1.5)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark set against the tuning pipeline.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--image-dir", default="public/benchmark")
    parser.add_argument("--images", nargs="*", default=DEFAULT_IMAGES)
    parser.add_argument("--prompt-profile", default="legacy")
    parser.add_argument("--selection-mode", default="manual")
    parser.add_argument("--variants", type=int, default=4)
    parser.add_argument("--benchmark-tag", default="benchmark_round1")
    parser.add_argument("--out", default="docs/benchmark_last_run.json")
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    results: list[dict] = []
    for image_name in args.images:
        image_path = image_dir / image_name
        if not image_path.exists():
            results.append({"image": image_name, "status": "missing"})
            continue
        fields = {
            "detail_level": "medium",
            "cleanup_strength": "medium",
            "num_variants": str(args.variants),
            "log_verbosity": "mid",
            "fabrication_style": "bold_signage",
            "prompt_profile": args.prompt_profile,
            "selection_mode": args.selection_mode,
            "benchmark_tag": args.benchmark_tag,
            "source_image_id": image_name,
            "source_frontend": "workbench",
        }
        try:
            created = _post_multipart(f"{args.api_base}/api/jobs", fields, image_path)
            job_id = created["job_id"]
            terminal = _wait_for_terminal(args.api_base, job_id)
            results.append(
                {
                    "image": image_name,
                    "job_id": job_id,
                    "status": terminal.get("status"),
                    "selected_candidate": terminal.get("selected_candidate"),
                    "prompt_version": terminal.get("prompt_version"),
                    "selection_reason": terminal.get("selection_reason"),
                    "quality_diagnostics": terminal.get("quality_diagnostics"),
                }
            )
        except error.HTTPError as http_err:
            results.append({"image": image_name, "status": "http_error", "code": http_err.code})
        except Exception as exc:  # noqa: BLE001
            results.append({"image": image_name, "status": "error", "error": str(exc)})

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"run_at": time.time(), "results": results}, indent=2), encoding="utf-8")
    print(f"Wrote benchmark summary to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
