import base64
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import settings

PROMPT = (
    "Illustration-first flat 2D vector style of a truck with bold weighted black lines, geometric abstraction, "
    "solid flat fills, pure black and white only, no anti-aliasing, no gradients, no shading, "
    "clean wheel-well curves and sharp body corners, minimalist icon-like composition."
)
NEGATIVE_PROMPT = (
    "photographic look, realistic texture, noisy micro-details, speckles, grill clutter, headlight clutter, "
    "blurry lines, messy background, painterly texture, gray wash, anti-aliased edges, soft shading"
)
FORCED_MODEL = "black-forest-labs/FLUX.1-Kontext-dev"
FALLBACK_MODELS = [
    "black-forest-labs/FLUX.1-Kontext-dev",
    "black-forest-labs/FLUX.1-Kontext-pro",
    "black-forest-labs/FLUX.1-dev",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "stabilityai/stable-diffusion-3.5-large",
    "stabilityai/stable-diffusion-3-medium",
]
CONTROLNET_MODEL = "lllyasviel/control_v11p_sd15_lineart"


def _encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _decode_base64_image(data: str, out_path: Path) -> None:
    raw = base64.b64decode(data)
    out_path.write_bytes(raw)


def _image_data_url(path: Path) -> str:
    return f"data:image/png;base64,{_encode_image(path)}"


def _download_image_from_url(client: httpx.Client, url: str, out_path: Path) -> None:
    response = client.get(url, timeout=120.0)
    response.raise_for_status()
    out_path.write_bytes(response.content)


def _resolve_model_id(client: httpx.Client) -> str:
    # Requirement: force Kontext-dev for generation path.
    # Best-effort availability check is logged elsewhere; selection remains fixed.
    try:
        client.get(f"{settings.siliconflow_base_url}/models", params={"type": "image", "sub_type": "image-to-image"}, timeout=20.0)
    except Exception:
        pass
    return FORCED_MODEL


def _local_mock_generation(normalized_path: Path, out_dir: Path, num_variants: int, detail_level: str) -> list[Path]:
    base = Image.open(normalized_path).convert("L")
    outputs: list[Path] = []
    for idx in range(1, num_variants + 1):
        img = base.copy()
        if detail_level == "high":
            img = ImageEnhance.Contrast(img).enhance(1.4)
        elif detail_level == "medium":
            img = ImageEnhance.Contrast(img).enhance(1.2)
        else:
            img = ImageEnhance.Contrast(img).enhance(1.05)

        edges = img.filter(ImageFilter.FIND_EDGES)
        bw = edges.point(lambda p: 0 if p > max(40, 95 - idx * 10) else 255, mode="1").convert("L")
        bw = ImageOps.invert(bw)
        out_path = out_dir / f"candidate_{idx}.png"
        bw.save(out_path, format="PNG")
        outputs.append(out_path)
    return outputs


def generate_candidates(
    normalized_path: Path, out_dir: Path, *, detail_level: str, num_variants: int
) -> tuple[list[Path], dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_started = time.perf_counter()
    strength = {"low": 0.45, "medium": 0.55, "high": 0.68}[detail_level]
    steps = {"low": 22, "medium": 30, "high": 40}[detail_level]
    cfg_scale = 12.0

    if not settings.siliconflow_api_key:
        outputs = _local_mock_generation(normalized_path, out_dir, num_variants, detail_level)
        trace = {
            "provider": "local_mock",
            "configured_model": FORCED_MODEL,
            "resolved_model": "local_mock_renderer",
            "detail_level": detail_level,
            "num_variants_requested": num_variants,
            "num_variants_generated": len(outputs),
            "steps": steps,
            "guidance_scale": cfg_scale,
            "strength": strength,
            "prompt": PROMPT,
            "negative_prompt": NEGATIVE_PROMPT,
            "provider_call_ms": 0.0,
            "total_generation_ms": round((time.perf_counter() - total_started) * 1000, 2),
            "reason": "SILICONFLOW_API_KEY missing",
        }
        return outputs, trace

    data_url = _image_data_url(normalized_path)

    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }

    provider_started = time.perf_counter()
    model_id = FORCED_MODEL
    parsed_payloads: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        client.headers.update(headers)
        model_id = _resolve_model_id(client)
        for _ in range(num_variants):
            payload = {
                "model": model_id,
                "prompt": PROMPT,
                "negative_prompt": NEGATIVE_PROMPT,
                # Match vectorize_old "Kontext image-edit" payload path.
                "image": data_url,
                "input_image": data_url,
                "control_image": data_url,
                "reference_image": data_url,
                "controlnet_model": CONTROLNET_MODEL,
                "guidance_scale": cfg_scale,
                "denoising_strength": strength,
                "num_inference_steps": steps,
                "prompt_enhancement": False,
                "output_format": "png",
            }
            response = client.post(f"{settings.siliconflow_base_url}/images/generations", headers=headers, json=payload)
            if response.status_code >= 400:
                body = response.text[:700].replace("\n", " ")
                raise RuntimeError(f"SiliconFlow error {response.status_code} (model={model_id}): {body}")
            parsed_payloads.append(response.json())
    provider_ms = round((time.perf_counter() - provider_started) * 1000, 2)

    outputs: list[Path] = []
    with httpx.Client(timeout=120.0) as client:
        for idx, parsed in enumerate(parsed_payloads, start=1):
            images = []
            if isinstance(parsed.get("images"), list):
                images = parsed["images"]
            elif isinstance(parsed.get("data"), list):
                images = parsed["data"]
            if not images:
                raise RuntimeError(f"Unexpected SiliconFlow response schema: {str(parsed)[:400]}")
            img = images[0]
            b64 = img.get("b64_json") or img.get("image")
            url = img.get("url")
            if not b64 and not url:
                raise RuntimeError("SiliconFlow response missing image payload")
            out_path = out_dir / f"candidate_{idx}.png"
            if b64:
                _decode_base64_image(b64, out_path)
            else:
                _download_image_from_url(client, str(url), out_path)
            outputs.append(out_path)

    trace = {
        "provider": "siliconflow",
        "configured_model": FORCED_MODEL,
        "resolved_model": model_id,
        "detail_level": detail_level,
        "num_variants_requested": num_variants,
        "num_variants_generated": len(outputs),
        "steps": steps,
        "guidance_scale": cfg_scale,
        "strength": strength,
        "controlnet_model": CONTROLNET_MODEL,
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "provider_call_ms": provider_ms,
        "total_generation_ms": round((time.perf_counter() - total_started) * 1000, 2),
    }
    return outputs, trace
