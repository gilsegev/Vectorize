from pathlib import Path
from collections import deque

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.config import settings
from app.models import CleanupStrength


def _quantile(values: list[int], q: float) -> int:
    if not values:
        return 0
    idx = int(max(0, min(len(values) - 1, round((len(values) - 1) * q))))
    return sorted(values)[idx]


def _largest_foreground_component(mask_bytes: bytearray, width: int, height: int) -> bytearray:
    visited = bytearray(width * height)
    best: list[int] = []
    deltas = (-1, 1, -width, width)
    for idx, value in enumerate(mask_bytes):
        if value == 0 or visited[idx]:
            continue
        queue: deque[int] = deque([idx])
        visited[idx] = 1
        comp: list[int] = []
        while queue:
            cur = queue.popleft()
            comp.append(cur)
            x = cur % width
            for d in deltas:
                nxt = cur + d
                if nxt < 0 or nxt >= len(mask_bytes):
                    continue
                nx = nxt % width
                if abs(nx - x) > 1:
                    continue
                if mask_bytes[nxt] != 0 and not visited[nxt]:
                    visited[nxt] = 1
                    queue.append(nxt)
        if len(comp) > len(best):
            best = comp

    out = bytearray(len(mask_bytes))
    for idx in best:
        out[idx] = 255
    return out


def _mask_coverage(mask_img: Image.Image) -> float:
    px = list(mask_img.convert("L").getdata())
    fg = sum(1 for v in px if v > 127)
    return fg / max(len(px), 1)


def _center_fallback_mask(width: int, height: int) -> Image.Image:
    left = int(width * 0.05)
    right = int(width * 0.95)
    top = int(height * 0.02)
    bottom = int(height * 0.98)
    data = bytearray(width * height)
    for y in range(top, bottom):
        row = y * width
        for x in range(left, right):
            data[row + x] = 255
    return Image.frombytes("L", (width, height), bytes(data))


def _derive_phase1_subject_mask(normalized_path: Path, mask_out: Path) -> None:
    rgb = Image.open(normalized_path).convert("RGB")
    width, height = rgb.size
    px = list(rgb.getdata())

    # Border-aware segmentation:
    # assume border pixels are mostly background, then flood-fill connected background
    # through color-similar areas.
    border_coords: list[int] = []
    border_band_x = max(2, int(width * 0.03))
    border_band_y = max(2, int(height * 0.03))
    for y in range(height):
        for x in range(width):
            if x < border_band_x or x >= width - border_band_x or y < border_band_y or y >= height - border_band_y:
                border_coords.append(y * width + x)

    br = sum(px[i][0] for i in border_coords) / max(len(border_coords), 1)
    bg = sum(px[i][1] for i in border_coords) / max(len(border_coords), 1)
    bb = sum(px[i][2] for i in border_coords) / max(len(border_coords), 1)

    dist: list[int] = []
    for (r, g, b) in px:
        dr = int(r - br)
        dg = int(g - bg)
        db = int(b - bb)
        dist.append(dr * dr + dg * dg + db * db)

    border_dist = [dist[i] for i in border_coords]
    bg_threshold = _quantile(border_dist, 0.90) + 900
    candidate_bg = bytearray(1 if d <= bg_threshold else 0 for d in dist)

    # Flood fill background from border across color-similar region.
    is_bg = bytearray(width * height)
    q: deque[int] = deque()
    for idx in border_coords:
        if candidate_bg[idx] and not is_bg[idx]:
            is_bg[idx] = 1
            q.append(idx)
    deltas = (-1, 1, -width, width)
    while q:
        cur = q.popleft()
        x = cur % width
        for d in deltas:
            nxt = cur + d
            if nxt < 0 or nxt >= width * height:
                continue
            nx = nxt % width
            if abs(nx - x) > 1:
                continue
            if candidate_bg[nxt] and not is_bg[nxt]:
                is_bg[nxt] = 1
                q.append(nxt)

    fg_mask = bytearray(255 if not is_bg[i] else 0 for i in range(width * height))
    fg_img = Image.frombytes("L", (width, height), bytes(fg_mask))
    fg_img = fg_img.filter(ImageFilter.MaxFilter(size=5)).filter(ImageFilter.MinFilter(size=5))

    cleaned = _largest_foreground_component(bytearray(fg_img.getdata()), width, height)
    mask = Image.frombytes("L", (width, height), bytes(cleaned))
    coverage = _mask_coverage(mask)

    # Safety fallback: if segmentation is degenerate, use conservative centered mask.
    if coverage < 0.03 or coverage > 0.95:
        mask = _center_fallback_mask(width, height)

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


def subject_mask_coverage(mask_path: Path) -> float:
    mask = Image.open(mask_path).convert("L")
    return round(_mask_coverage(mask), 4)


def cleanup_raster(
    candidate_path: Path,
    binary_out: Path,
    preview_out: Path,
    strength: CleanupStrength,
    subject_mask_path: Path | None = None,
    *,
    threshold_bias: int = 0,
    min_component_px: int = 20,
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
