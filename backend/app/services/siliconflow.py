import base64
import shutil
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import settings
from app.models import PromptProfile
from app.services.tuning import LEGACY_NEGATIVE_PROMPT, LEGACY_PROMPT, resolve_generation_prompt

PROMPT = LEGACY_PROMPT
NEGATIVE_PROMPT = LEGACY_NEGATIVE_PROMPT
FORCED_MODEL = "black-forest-labs/FLUX.1-Kontext-dev"
INKING_PROMPT = (
    "Refine the provided candidate into professional subject-preserving vector line art. "
    "Keep the same subject identity, pose, and silhouette exactly; only improve line clarity and smoothness. "
    "Uniform line weights, bold black ink outlines, clean Ligne claire style, flat 2D illustration, zero noise, high contrast."
)
FALLBACK_MODELS = [
    "black-forest-labs/FLUX.1-Kontext-dev",
    "black-forest-labs/FLUX.1-Kontext-pro",
    "black-forest-labs/FLUX.1-dev",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "stabilityai/stable-diffusion-3.5-large",
    "stabilityai/stable-diffusion-3-medium",
]
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


def _post_generation_with_retries(client: httpx.Client, payload: dict[str, Any], model_id: str) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = client.post(f"{settings.siliconflow_base_url}/images/generations", json=payload)
            if response.status_code >= 400:
                body = response.text[:700].replace("\n", " ")
                raise RuntimeError(f"SiliconFlow error {response.status_code} (model={model_id}): {body}")
            return response.json()
        except RuntimeError:
            raise
        except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError, httpx.WriteError) as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(float(attempt))
                continue
            break

    raise RuntimeError(
        f"SiliconFlow generation request failed after retries (model={model_id}): "
        f"{last_exc.__class__.__name__ if last_exc else 'unknown error'}: {last_exc}"
    )


def _extract_first_image_payload(parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    images = []
    if isinstance(parsed.get("images"), list):
        images = parsed["images"]
    elif isinstance(parsed.get("data"), list):
        images = parsed["data"]
    if not images:
        raise RuntimeError(f"Unexpected SiliconFlow response schema: {str(parsed)[:400]}")
    img = images[0]
    return (img.get("b64_json") or img.get("image"), img.get("url"))


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
    normalized_path: Path, out_dir: Path, *, detail_level: str, num_variants: int, prompt_profile: PromptProfile = PromptProfile.legacy
) -> tuple[list[Path], dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_started = time.perf_counter()
    strength = {"low": 0.45, "medium": 0.55, "high": 0.68}[detail_level]
    steps = {"low": 22, "medium": 30, "high": 40}[detail_level]
    cfg_scale = 12.0
    prompt_payload = resolve_generation_prompt(prompt_profile)
    resolved_prompt = prompt_payload["prompt"]
    resolved_negative_prompt = prompt_payload["negative_prompt"]
    resolved_profile = prompt_payload["prompt_profile"]
    prompt_version = prompt_payload["prompt_version"]

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
            "prompt_profile": resolved_profile,
            "prompt_version": prompt_version,
            "prompt": resolved_prompt,
            "negative_prompt": resolved_negative_prompt,
            "provider_call_ms": 0.0,
            "total_generation_ms": round((time.perf_counter() - total_started) * 1000, 2),
            "reason": "SILICONFLOW_API_KEY missing",
        }
        return outputs, trace

    data_url = _image_data_url(normalized_path)

    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
        "Connection": "close",
    }

    provider_started = time.perf_counter()
    model_id = FORCED_MODEL
    parsed_payloads: list[dict[str, Any]] = []
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=30.0, pool=30.0)
    with httpx.Client(timeout=timeout) as client:
        client.headers.update(headers)
        model_id = _resolve_model_id(client)
        for _ in range(num_variants):
            payload = {
                "model": model_id,
                "prompt": resolved_prompt,
                "negative_prompt": resolved_negative_prompt,
                # Keep payload minimal for current SiliconFlow image-edit schema.
                "image": data_url,
                "guidance_scale": cfg_scale,
                "num_inference_steps": steps,
                "prompt_enhancement": False,
                "output_format": "png",
            }
            parsed_payloads.append(_post_generation_with_retries(client, payload, model_id))
    provider_ms = round((time.perf_counter() - provider_started) * 1000, 2)

    outputs: list[Path] = []
    with httpx.Client(timeout=120.0) as client:
        for idx, parsed in enumerate(parsed_payloads, start=1):
            b64, url = _extract_first_image_payload(parsed)
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
        "prompt_profile": resolved_profile,
        "prompt_version": prompt_version,
        "prompt": resolved_prompt,
        "negative_prompt": resolved_negative_prompt,
        "provider_call_ms": provider_ms,
        "total_generation_ms": round((time.perf_counter() - total_started) * 1000, 2),
    }
    return outputs, trace


def refine_candidate_with_inking(
    candidate_path: Path,
    subject_mask_path: Path | None,
    refined_out: Path,
    *,
    denoising_strength: float = 0.42,
) -> dict[str, Any]:
    started = time.perf_counter()
    refined_out.parent.mkdir(parents=True, exist_ok=True)

    if not settings.siliconflow_api_key:
        shutil.copyfile(candidate_path, refined_out)
        return {
            "provider": "local_mock",
            "configured_model": FORCED_MODEL,
            "resolved_model": "local_mock_renderer",
            "denoising_strength": denoising_strength,
            "controlnet_model": "none",
            "prompt": INKING_PROMPT,
            "provider_call_ms": 0.0,
            "total_inking_ms": round((time.perf_counter() - started) * 1000, 2),
            "reason": "SILICONFLOW_API_KEY missing",
        }

    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
        "Connection": "close",
    }
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=30.0, pool=30.0)

    candidate_data_url = _image_data_url(candidate_path)
    control_data_url = _image_data_url(subject_mask_path) if subject_mask_path and subject_mask_path.exists() else None
    controlnet_models = [
        "lllyasviel/control_v11p_sd15_canny",
        "lllyasviel/control_v11f1p_sd15_depth",
    ]

    provider_started = time.perf_counter()
    model_id = FORCED_MODEL
    parsed: dict[str, Any] | None = None
    last_error: Exception | None = None
    with httpx.Client(timeout=timeout) as client:
        client.headers.update(headers)
        model_id = _resolve_model_id(client)
        for controlnet_model in controlnet_models:
            payload = {
                "model": model_id,
                "prompt": INKING_PROMPT,
                "image": candidate_data_url,
                "input_image": candidate_data_url,
                "guidance_scale": 10.0,
                "num_inference_steps": 26,
                "denoising_strength": denoising_strength,
                "prompt_enhancement": False,
                "output_format": "png",
            }
            if control_data_url:
                payload["control_image"] = control_data_url
                payload["reference_image"] = control_data_url
                payload["controlnet_model"] = controlnet_model
            try:
                parsed = _post_generation_with_retries(client, payload, model_id)
                selected_controlnet = controlnet_model if control_data_url else "none"
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                parsed = None
                selected_controlnet = controlnet_model
        if parsed is None:
            raise RuntimeError(f"Inking pass failed for all controlnet variants: {last_error}")
    provider_ms = round((time.perf_counter() - provider_started) * 1000, 2)

    b64, url = _extract_first_image_payload(parsed)
    if not b64 and not url:
        raise RuntimeError("SiliconFlow inking response missing image payload")
    if b64:
        _decode_base64_image(b64, refined_out)
    else:
        with httpx.Client(timeout=120.0) as client:
            _download_image_from_url(client, str(url), refined_out)

    return {
        "provider": "siliconflow",
        "configured_model": FORCED_MODEL,
        "resolved_model": model_id,
        "denoising_strength": denoising_strength,
        "controlnet_model": selected_controlnet,
        "prompt": INKING_PROMPT,
        "provider_call_ms": provider_ms,
        "total_inking_ms": round((time.perf_counter() - started) * 1000, 2),
    }
