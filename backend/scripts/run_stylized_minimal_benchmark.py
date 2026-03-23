import argparse
import csv
import json
import mimetypes
import time
from pathlib import Path
from urllib import error, request

DEFAULT_IMAGES = [
    "car.jpg",
    "dog.jpg",
    "portrait_1.jpg",
    "product.jpg",
]
DEFAULT_ANCHOR_IMAGES = [
    "car.jpg",
    "dog.jpg",
]
DEFAULT_STYLIZED_PROFILES = [
    "stylized_v1_detail_preserving",
    "stylized_v2_balanced_cartoon",
    "stylized_v3_bold_cartoon",
    "stylized_v4_graphic_poster",
]
DEFAULT_ANCHOR_PROFILES = [
    "legacy",
    "balanced_default",
]


def _post_multipart(url: str, fields: dict[str, str], file_path: Path) -> dict:
    boundary = "----VectorizeStylizedBoundary987654321"
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
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_terminal(api_base: str, job_id: str, timeout_sec: float = 1800.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        payload = _get_json(f"{api_base}/api/jobs/{job_id}?view=workbench")
        if payload.get("status") in {"completed", "failed", "waiting_for_selection"}:
            return payload
        time.sleep(1.5)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal stylized tuning benchmark: stylized profiles on full set, legacy/balanced on anchor subset."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--image-dir", default="public/benchmark")
    parser.add_argument("--images", nargs="*", default=DEFAULT_IMAGES)
    parser.add_argument("--anchor-images", nargs="*", default=DEFAULT_ANCHOR_IMAGES)
    parser.add_argument("--stylized-profiles", nargs="*", default=DEFAULT_STYLIZED_PROFILES)
    parser.add_argument("--anchor-profiles", nargs="*", default=DEFAULT_ANCHOR_PROFILES)
    parser.add_argument("--variants", type=int, default=1)
    parser.add_argument("--benchmark-tag", default="stylized-minimal")
    parser.add_argument("--out-json", default="docs/stylized_minimal_last_run.json")
    parser.add_argument("--out-csv", default="docs/stylized_minimal_last_run.csv")
    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    anchors = set(args.anchor_images)
    rows: list[dict[str, object]] = []

    run_started = time.time()
    for image_name in args.images:
        image_path = image_dir / image_name
        if not image_path.exists():
            rows.append(
                {
                    "image": image_name,
                    "is_anchor": image_name in anchors,
                    "profile": "",
                    "job_id": "",
                    "status": "missing_image",
                    "error": f"Image not found: {image_path}",
                }
            )
            continue

        profiles = list(args.stylized_profiles)
        if image_name in anchors:
            profiles = list(args.anchor_profiles) + profiles

        for profile in profiles:
            fields = {
                "detail_level": "medium",
                "cleanup_strength": "medium",
                "num_variants": str(args.variants),
                "log_verbosity": "mid",
                "fabrication_style": "bold_signage",
                "prompt_profile": profile,
                "selection_mode": "manual",
                "benchmark_tag": f"{args.benchmark_tag}-{profile}",
                "source_image_id": image_name,
                "source_frontend": "workbench",
            }
            print(f"[run] image={image_name} profile={profile}", flush=True)
            try:
                created = _post_multipart(f"{args.api_base}/api/jobs", fields, image_path)
                job_id = str(created["job_id"])
                terminal = _wait_for_terminal(args.api_base, job_id)
                quality = terminal.get("quality_diagnostics", {}) or {}
                cnc = terminal.get("cnc_metrics", {}) or {}
                rows.append(
                    {
                        "image": image_name,
                        "is_anchor": image_name in anchors,
                        "profile": profile,
                        "job_id": job_id,
                        "status": terminal.get("status"),
                        "error": terminal.get("error"),
                        "selected_candidate": terminal.get("selected_candidate"),
                        "prompt_version": terminal.get("prompt_version"),
                        "node_count": cnc.get("node_count"),
                        "mse_fidelity": cnc.get("mse_fidelity"),
                        "small_component_count": quality.get("small_component_count"),
                        "interior_line_density": quality.get("interior_line_density"),
                        "output_dir": terminal.get("output_dir"),
                    }
                )
            except error.HTTPError as http_err:
                body = ""
                try:
                    body = http_err.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                rows.append(
                    {
                        "image": image_name,
                        "is_anchor": image_name in anchors,
                        "profile": profile,
                        "job_id": "",
                        "status": "http_error",
                        "error": f"{http_err.code}: {body[:500]}",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "image": image_name,
                        "is_anchor": image_name in anchors,
                        "profile": profile,
                        "job_id": "",
                        "status": "error",
                        "error": str(exc),
                    }
                )

    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "run_started_unix": run_started,
        "run_completed_unix": time.time(),
        "api_base": args.api_base,
        "image_dir": str(image_dir),
        "images": args.images,
        "anchor_images": args.anchor_images,
        "stylized_profiles": args.stylized_profiles,
        "anchor_profiles": args.anchor_profiles,
        "rows": rows,
    }
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    fieldnames = [
        "image",
        "is_anchor",
        "profile",
        "job_id",
        "status",
        "error",
        "selected_candidate",
        "prompt_version",
        "node_count",
        "mse_fidelity",
        "small_component_count",
        "interior_line_density",
        "output_dir",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote JSON report: {out_json}")
    print(f"Wrote CSV report:  {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
