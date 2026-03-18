from collections import deque
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps

POTRACE_TURDSIZE = "100"
POTRACE_ALPHAMAX = "0"
STAR_OPT = "0.9"
TEXT_OPT = "0.4"
MIN_TEXT_COMPONENT = 40


def _connected_components(binary: list[int], width: int, height: int) -> list[list[int]]:
    visited = bytearray(len(binary))
    components: list[list[int]] = []
    deltas = (-1, 1, -width, width, -width - 1, -width + 1, width - 1, width + 1)
    for idx, value in enumerate(binary):
        if value != 0 or visited[idx]:
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
                if nxt < 0 or nxt >= len(binary):
                    continue
                nx = nxt % width
                if abs(nx - x) > 1:
                    continue
                if binary[nxt] == 0 and not visited[nxt]:
                    visited[nxt] = 1
                    queue.append(nxt)
        components.append(comp)
    return components


def _mask_for_components(width: int, height: int, components: list[list[int]]) -> Image.Image:
    px = bytearray([255] * (width * height))
    for comp in components:
        for idx in comp:
            px[idx] = 0
    return Image.frombytes("L", (width, height), bytes(px))


def _run_potrace(mask: Image.Image, out_svg: Path, opt_tolerance: str) -> None:
    explicit_candidates = [
        Path("D:/tools/potrace/potrace-1.16.win64/potrace.exe"),
        Path("D:/tools/potrace/potrace-1.16.win32/potrace.exe"),
    ]
    potrace_path = shutil.which("potrace")
    if potrace_path:
        potrace = potrace_path
    else:
        found = next((str(p) for p in explicit_candidates if p.exists()), "")
        potrace = found or None
    if not potrace:
        _fallback_trace_mask(mask, out_svg)
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        pbm_path = Path(tmpdir) / "mask.pbm"
        mask.convert("1").save(pbm_path, format="PPM")
        cmd = [
            potrace,
            str(pbm_path),
            "-s",
            "--turdsize",
            POTRACE_TURDSIZE,
            "--alphamax",
            POTRACE_ALPHAMAX,
            "--opttolerance",
            opt_tolerance,
            "-o",
            str(out_svg),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)


def _fallback_trace_mask(mask: Image.Image, out_svg: Path) -> None:
    width, height = mask.size
    px = list(mask.convert("L").getdata())
    segments: list[str] = []
    step = 2
    for y in range(0, height, step):
        x = 0
        while x < width:
            idx = y * width + x
            while x < width and px[idx] > 127:
                x += 1
                idx = y * width + x if x < width else idx
            if x >= width:
                break
            start = x
            idx = y * width + x
            while x < width and px[idx] <= 127:
                x += 1
                idx = y * width + x if x < width else idx
            end = x
            if end > start:
                segments.append(
                    f"M {start} {y} L {end} {y} L {end} {min(y + step, height)} L {start} {min(y + step, height)} Z"
                )
    if not segments:
        segments.append("M 0 0 L 1 0 L 1 1 L 0 1 Z")
    path_markup = "".join([f'<path d="{d}" fill="black" stroke="none" />' for d in segments])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f"{path_markup}\n"
        "</svg>"
    )
    out_svg.write_text(svg, encoding="utf-8")


def _extract_svg_paths(svg_path: Path) -> list[str]:
    if not svg_path.exists():
        return []
    tree = ET.parse(svg_path)
    root = tree.getroot()
    paths: list[str] = []
    for elem in root.iter():
        if elem.tag.endswith("path"):
            d = elem.attrib.get("d")
            if d:
                paths.append(d)
    return paths


def _merge_svg(width: int, height: int, star_paths: list[str], text_paths: list[str], svg_out: Path) -> None:
    all_paths = star_paths + text_paths
    if not all_paths:
        all_paths = ["M 0 0 L 1 0 L 1 1 L 0 1 Z"]
    path_markup = "\n".join([f'<path d="{d}" fill="black" stroke="none" />' for d in all_paths])
    merged = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="100%" height="100%" fill="white" />\n'
        f"{path_markup}\n"
        "</svg>"
    )
    svg_out.write_text(merged, encoding="utf-8")


def vectorize(binary_path: Path, svg_out: Path, preview_out: Path) -> None:
    img = Image.open(binary_path).convert("L")
    img = ImageOps.autocontrast(img).point(lambda p: 0 if p < 128 else 255, mode="L")
    width, height = img.size
    binary = list(img.getdata())
    components = _connected_components(binary, width, height)

    largest = max(components, key=len) if components else []
    text_components = [c for c in components if len(c) >= MIN_TEXT_COMPONENT and c is not largest]

    star_mask = _mask_for_components(width, height, [largest] if largest else [])
    text_mask = _mask_for_components(width, height, text_components)

    with tempfile.TemporaryDirectory() as tmpdir:
        star_svg = Path(tmpdir) / "star.svg"
        text_svg = Path(tmpdir) / "text.svg"
        _run_potrace(star_mask, star_svg, STAR_OPT)
        _run_potrace(text_mask, text_svg, TEXT_OPT)
        _merge_svg(width, height, _extract_svg_paths(star_svg), _extract_svg_paths(text_svg), svg_out)

    preview = ImageOps.colorize(img, black="#000000", white="#ffffff")
    preview.save(preview_out, format="PNG")
