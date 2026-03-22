import io
import time
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw


def _sample_png_bytes() -> bytes:
    img = Image.new("RGB", (320, 220), color="white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((60, 25, 260, 205), outline="black", width=7)
    draw.line((50, 110, 270, 110), fill="black", width=5)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _create_job(client, num_variants: int = 1):
    files = {"file": ("input.png", _sample_png_bytes(), "image/png")}
    data = {
        "detail_level": "medium",
        "cleanup_strength": "medium",
        "num_variants": str(num_variants),
    }
    response = client.post("/api/jobs", files=files, data=data)
    assert response.status_code == 200
    return response.json()["job_id"]


def _poll_job(client, job_id: str, *, terminal=("completed", "failed", "waiting_for_selection"), timeout=8.0):
    deadline = time.time() + timeout
    payload = None
    while time.time() < deadline:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        payload = resp.json()
        if payload["status"] in terminal:
            return payload
        time.sleep(0.2)
    return payload


def test_happy_path_single_variant(client):
    job_id = _create_job(client, num_variants=1)
    payload = _poll_job(client, job_id, terminal=("completed", "failed"))
    assert payload["status"] == "completed"

    artifacts = payload["artifacts"]
    for key in ["original", "normalized", "grayscale", "edge_map", "binary", "cleanup_preview", "final_svg", "final_preview"]:
        assert artifacts[key], f"missing {key}"
    assert payload.get("prompt_version")
    assert "quality_diagnostics" in payload
    assert payload["quality_diagnostics"].get("face_region_density") is None

    svg_resp = client.get(f"/api/jobs/{job_id}/download/svg")
    assert svg_resp.status_code == 200
    root = ElementTree.fromstring(svg_resp.content)
    assert root.tag.endswith("svg")
    assert payload.get("batch_run_id")
    log_resp = client.get(f"/api/jobs/{job_id}/log")
    assert log_resp.status_code == 200
    assert "Job completed successfully" in log_resp.text
    assert "Generation provider call" in log_resp.text
    assert "configured_model=" in log_resp.text


def test_manual_variant_selection_flow(client):
    job_id = _create_job(client, num_variants=3)
    waiting = _poll_job(client, job_id)
    assert waiting["status"] == "waiting_for_selection"
    assert len(waiting["artifacts"]["candidates"]) == 3
    assert waiting.get("candidate_scores")

    bad = client.post(f"/api/jobs/{job_id}/select-variant", json={"candidate": "candidate_99.png"})
    assert bad.status_code == 400

    selected = client.post(f"/api/jobs/{job_id}/select-variant", json={"candidate": "candidate_2.png"})
    assert selected.status_code == 200

    completed = _poll_job(client, job_id, terminal=("completed", "failed"))
    assert completed["status"] == "completed"
    assert completed["selected_candidate"] == "candidate_2.png"
    assert completed["settings"]["log_verbosity"] == "mid"
    assert completed.get("selection_reason")


def test_invalid_file_type_rejected(client):
    files = {"file": ("input.txt", b"not an image", "text/plain")}
    response = client.post("/api/jobs", files=files)
    assert response.status_code == 400


def test_download_before_completion_rejected(client):
    job_id = _create_job(client, num_variants=2)
    # Most runs should still be waiting for manual selection at this point.
    response = client.get(f"/api/jobs/{job_id}/download/svg")
    assert response.status_code in (404, 409)


def test_clear_log_endpoint(client):
    job_id = _create_job(client, num_variants=1)
    payload = _poll_job(client, job_id, terminal=("completed", "failed"))
    assert payload["status"] == "completed"
    before = client.get(f"/api/jobs/{job_id}/log")
    assert before.status_code == 200
    assert before.text.strip()
    cleared = client.post(f"/api/jobs/{job_id}/log/clear")
    assert cleared.status_code == 200
    after = client.get(f"/api/jobs/{job_id}/log")
    assert after.status_code == 200
    assert after.text == ""
