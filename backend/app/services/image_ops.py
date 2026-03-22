from pathlib import Path
from collections import deque

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import settings
from app.models import CleanupStrength


def _derive_phase1_subject_mask(normalized_path: Path, mask_out: Path) -> None:
    rgb = Image.open(normalized_path).convert("RGB")
    gray = ImageOps.grayscale(rgb)
    # White-ish background stays background; subject region becomes foreground.
    mask = gray.point(lambda p: 255 if p < 245 else 0, mode="L")
    mask = mask.filter(ImageFilter.MaxFilter(size=5)).filter(ImageFilter.MinFilter(size=5))
    mask.save(mask_out, format="PNG")


def normalize_upload(upload_path: Path, output_path: Path) -> None:
    img = Image.open(upload_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    max_dimension = settings.max_dimension
    scale = min(max_dimension / max(img.width, 1), max_dimension / max(img.height, 1), 1.0)
    if scale < 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    img.save(output_path, format="PNG")


def preprocess(
    normalized_path: Path,
    grayscale_out: Path,
    edge_map_out: Path,
    detail_level: str,
    subject_mask_out: Path | None = None,
) -> None:
    img = Image.open(normalized_path).convert("L")
    gray = img.filter(ImageFilter.GaussianBlur(radius=1.0))

    contrast = {
        "low": 1.0,
        "medium": 1.2,
        "high": 1.35,
    }[detail_level]
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    gray.save(grayscale_out, format="PNG")

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    edges.save(edge_map_out, format="PNG")
    if subject_mask_out is not None:
        _derive_phase1_subject_mask(normalized_path, subject_mask_out)


def cleanup_raster(
    candidate_path: Path,
    binary_out: Path,
    preview_out: Path,
    strength: CleanupStrength,
    subject_mask_path: Path | None = None,
    *,
    threshold_bias: int = 0,
    min_component_px: int = 40,
    speck_morph: int = 0,
) -> None:
    img = Image.open(candidate_path).convert("L")

    width, height = img.size
    gray = list(ImageOps.autocontrast(img).getdata())

    # Strict binary crush using Otsu (equivalent intent to THRESH_BINARY + OTSU).
    histogram = [0] * 256
    for value in gray:
        histogram[value] += 1
    total = width * height
    sum_all = sum(i * h for i, h in enumerate(histogram))
    sum_bg = 0.0
    weight_bg = 0.0
    max_var = -1.0
    otsu_threshold = 127
    for t in range(256):
        weight_bg += histogram[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * histogram[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_all - sum_bg) / weight_fg
        between = weight_bg * weight_fg * ((mean_bg - mean_fg) ** 2)
        if between > max_var:
            max_var = between
            otsu_threshold = t

    adjusted_threshold = max(0, min(255, otsu_threshold + threshold_bias))

    # Black islands are <= threshold.
    black = bytearray(1 if px <= adjusted_threshold else 0 for px in gray)

    # Connected component filtering.
    visited = bytearray(len(black))
    components: list[list[int]] = []
    neighbor_deltas = (-1, 1, -width, width, -width - 1, -width + 1, width - 1, width + 1)
    for idx, is_black in enumerate(black):
        if not is_black or visited[idx]:
            continue
        queue: deque[int] = deque([idx])
        visited[idx] = 1
        comp: list[int] = []
        while queue:
            current = queue.popleft()
            comp.append(current)
            x = current % width
            for delta in neighbor_deltas:
                nxt = current + delta
                if nxt < 0 or nxt >= len(black):
                    continue
                nx = nxt % width
                if abs(nx - x) > 1:
                    continue
                if black[nxt] and not visited[nxt]:
                    visited[nxt] = 1
                    queue.append(nxt)
        components.append(comp)

    # Keep medium/large components, remove tiny islands.
    kept = [comp for comp in components if len(comp) >= min_component_px]
    largest: list[int] = max(kept, key=len) if kept else []

    filtered = bytearray(255 for _ in range(len(black)))
    for comp in kept:
        for idx in comp:
            filtered[idx] = 0

    # Smooth only the largest component to avoid melting medium text features.
    filtered_img = Image.frombytes("L", (width, height), bytes(filtered))
    if largest:
        if strength == CleanupStrength.low:
            smooth_size = 3
        elif strength == CleanupStrength.medium:
            smooth_size = 5
        else:
            smooth_size = 7
        if speck_morph > 0:
            smooth_size = min(9, smooth_size + (2 * speck_morph))
        smoothed = filtered_img.filter(ImageFilter.MinFilter(size=smooth_size)).filter(ImageFilter.MaxFilter(size=smooth_size))
        smoothed_px = list(smoothed.getdata())
        final_px = bytearray(filtered)
        for idx in largest:
            final_px[idx] = smoothed_px[idx]
        cleaned = Image.frombytes("L", (width, height), bytes(final_px))
    else:
        cleaned = filtered_img

    # Enforce exact 2-color output with no anti-aliasing before vectorization.
    cleaned = cleaned.point(lambda p: 0 if p < 128 else 255, mode="1").convert("L")
    cleaned.save(binary_out, format="PNG")

    preview = ImageOps.colorize(cleaned, black="#111111", white="#f5f5f5")
    preview.save(preview_out, format="PNG")
