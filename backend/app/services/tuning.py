from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.config import settings
from app.models import PromptProfile

LEGACY_PROMPT = (
    "Convert the provided input image into subject-preserving decal-ready line art. "
    "Keep the same subject identity, pose, silhouette, and main internal forms from the uploaded image. "
    "Render in clean black-and-white flat 2D vector style with bold outlines, no gradients, no shading, no anti-aliasing."
)
LEGACY_NEGATIVE_PROMPT = (
    "different subject, changed object category, swapped anatomy, added vehicle parts, added text/logo, "
    "mesh, honeycomb, dots, stippling, photographic texture, realistic reflections, tiny details, gradients, "
    "noise, grain, dust, grit, messy, blurry, low-res, speckled, anti-aliased edges, soft shading"
)

PROMPT_REGISTRY: dict[PromptProfile, dict[str, str]] = {
    PromptProfile.balanced_default: {
        "prompt": (
            "stylized professional black-ink line art of the uploaded image, clear cartoonized silhouette with preserved structure, "
            "clean confident contours, keep distinctive internal subject features, simplify low-value texture only, "
            "preserve identity cues and key structural landmarks from the source image, polished decal-ready look on plain light background, "
            "do not change subject category or anatomy"
        ),
        "negative_prompt": (
            "generic simplification, erased internal features, blank interior surfaces, muddy contour breaks, over-thinning key lines, "
            "subject category swap, changed object type, changed anatomy, person-to-vehicle substitution, icon-to-truck substitution, "
            "messy background, watercolor, painterly texture, photoreal shading, noisy micro speckles, duplicated geometry, deformed structure"
        ),
    },
    PromptProfile.balanced_fallback_base_control: {
        "prompt": (
            "clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, "
            "preserved subject identity cues, preserved important structural features, selective line placement, clean silhouettes, "
            "minimal but confident key features, reduced low-value texture, smooth black ink lines on plain light background, "
            "hand-drawn editorial illustration quality"
        ),
        "negative_prompt": (
            "messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive texture, "
            "too many interior lines, noisy micro-detail, cluttered low-value detail, sketchy scribbles, duplicated features, "
            "deformed structure, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture"
        ),
    },
    PromptProfile.realistic_seed: {
        "prompt": (
            "high-fidelity professional pen-and-ink drawing of the uploaded image, accurate structure, minimal stylization, clean contour emphasis, "
            "preserved subject identity cues, preserved important structural features, subtle interior detail, natural proportions, "
            "retain essential source detail and shape relationships, smooth black ink contours, polished hand-drawn line illustration on a plain light background"
        ),
        "negative_prompt": (
            "cartoon simplification, exaggerated features, generic structure, posterized look, graphic novel style, comic-book inking, manga style, "
            "logo style, stencil effect, aggressive abstraction, excessive black fill, messy background, photoreal shading, painterly texture, watercolor, gray wash, "
            "crosshatching, dense texture, sketchy scribbles, subject category swap, changed object type, changed anatomy"
        ),
    },
    PromptProfile.stylized_seed_do_not_default: {
        "prompt": (
            "clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, "
            "preserve subject identity cues, preserve distinctive structural features, simplify texture to major forms only, "
            "simplify secondary surfaces and interior details, selective line placement, clean silhouettes, minimal but readable key features, "
            "polished hand-drawn editorial line art on a plain light background"
        ),
        "negative_prompt": (
            "excessive texture, dense surface detail, too many interior lines, busy linework, over-simplification of defining features, generic structure, "
            "blocky abstraction, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, sketchy scribbles, "
            "duplicated features, deformed structure, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture"
        ),
    },
    PromptProfile.stylized_v1_detail_preserving: {
        "prompt": (
            "stylized professional black-ink line art of the uploaded image, clear cartoonized silhouette with preserved structure, "
            "clean confident contours, keep distinctive internal subject features, simplify low-value texture only, "
            "preserve identity cues and key structural landmarks from the source image, polished decal-ready look on plain light background, "
            "do not change subject category or anatomy"
        ),
        "negative_prompt": (
            "generic simplification, erased internal features, blank interior surfaces, muddy contour breaks, over-thinning key lines, "
            "subject category swap, changed object type, changed anatomy, person-to-vehicle substitution, icon-to-truck substitution, "
            "messy background, watercolor, painterly texture, photoreal shading, noisy micro speckles, duplicated geometry, deformed structure"
        ),
    },
    PromptProfile.stylized_v2_balanced_cartoon: {
        "prompt": (
            "cartoon-leaning yet subject-faithful black-and-white line illustration of the uploaded image, bold outer contours, "
            "selective interior detail, simplified forms, crisp high-contrast inking, preserve signature shape cues and important structural landmarks, "
            "clean production-ready stylization on plain light background, keep the same subject category as input"
        ),
        "negative_prompt": (
            "flat generic silhouette, missing identity landmarks, collapsed structure, over-detailed texture noise, "
            "subject category swap, changed object type, changed anatomy, person-to-vehicle substitution, icon-to-truck substitution, "
            "messy line chatter, photoreal shading, sketchy rough lines, comic halftone dots, gradient fills, watercolor wash"
        ),
    },
    PromptProfile.stylized_v3_bold_cartoon: {
        "prompt": (
            "strongly stylized cartoon ink rendering of the uploaded image with bold contour hierarchy, thicker key outlines, "
            "intentional simplification of secondary lines, keep recognizable subject identity and major structural geometry, "
            "high-impact graphic decal style with clean black paths and no background clutter, keep original subject category"
        ),
        "negative_prompt": (
            "identity drift, altered proportions, removed key landmarks, chaotic texture, shaky sketch strokes, over-fragmented interior lines, "
            "subject category swap, changed object type, changed anatomy, person-to-vehicle substitution, icon-to-truck substitution, "
            "photoreal lighting, gray shading, painterly effects, soft blurred edges, excessive tiny artifacts"
        ),
    },
    PromptProfile.stylized_v4_graphic_poster: {
        "prompt": (
            "graphic poster-style cartoon line art from the uploaded image, bold simplified masses, assertive outer silhouette, "
            "minimal but strategic interior line accents, preserve core identity cues and dominant structural features, "
            "clean geometric black ink shapes suitable for decal fabrication, preserve source subject category"
        ),
        "negative_prompt": (
            "subject deformation, unreadable structure, random missing parts, muddy edges, fine noise texture, crosshatching, engraving look, "
            "subject category swap, changed object type, changed anatomy, person-to-vehicle substitution, icon-to-truck substitution, "
            "photoreal shadows, painterly brush texture, busy background, low-contrast gray tones"
        ),
    },
    PromptProfile.base_professional_pen: {
        "prompt": (
            "clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, "
            "simplified interior detail, preserved facial identity, preserved natural expression, selective line placement, "
            "clean silhouettes, minimal but confident facial features, minimal fabric folds, reduced hair strand detail, "
            "smooth black ink lines on plain light background, hand-drawn editorial illustration quality"
        ),
        "negative_prompt": (
            "messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, "
            "too many fabric folds, excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, "
            "sketchy scribbles, duplicated features, deformed hands, cluttered interior lines, comic-book exaggeration, "
            "cartoon style, manga style, engraving texture, woodcut texture"
        ),
    },
    PromptProfile.stronger_polish: {
        "prompt": (
            "clean professional pen illustration, highly selective linework, only essential contours and facial features, "
            "simplified hair masses instead of individual strands, simplified clothing with only major folds, "
            "elegant black ink contours, quiet interior detail, natural human likeness, readable expression, "
            "polished hand-drawn look, minimal line clutter, premium editorial line art"
        ),
        "negative_prompt": (
            "busy linework, scratchy pen marks, excess texture, too many contour lines, too many smile lines, "
            "too much cheek detail, too many eyelid lines, detailed skin texture, dense hair texture, "
            "dense clothing wrinkles, comic inking, stylized cartoon features, dramatic graphic-novel shading, "
            "hatch marks, stippling, rough sketch"
        ),
    },
    PromptProfile.realism_preserving: {
        "prompt": (
            "naturalistic pen-and-ink portrait drawing, accurate likeness, restrained simplification, clean contour emphasis, "
            "minimal shading, subtle interior detail, realistic proportions, natural facial structure, "
            "lightly simplified hair and clothing, polished black line drawing"
        ),
        "negative_prompt": (
            "cartoon simplification, exaggerated features, icon-like face, overly flat shapes, posterized look, "
            "logo style, stencil effect, aggressive abstraction"
        ),
    },
    PromptProfile.variant_a_preserve_likeness: {
        "prompt": (
            "clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, "
            "simplified interior detail, preserved facial identity, preserved adult facial individuality, preserved natural expression, "
            "natural facial structure, selective line placement, clean silhouettes, minimal but distinctive facial features, "
            "lightly simplified hair and clothing, smooth black ink lines on plain light background, polished hand-drawn illustration"
        ),
        "negative_prompt": (
            "generic face simplification, overly idealized face, blocky hair masses, posterized facial structure, messy background, "
            "photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, too many fabric folds, "
            "excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, "
            "deformed hands, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture"
        ),
    },
    PromptProfile.variant_b_selective_simplification: {
        "prompt": (
            "clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, "
            "simplified interior detail, preserve facial identity and expression, preserve distinctive facial cues, "
            "simplify clothing to major folds only, simplify hair into clean flowing masses with limited strand detail, "
            "selective line placement, clean silhouettes, minimal but readable facial features, polished hand-drawn editorial line art "
            "on a plain light background"
        ),
        "negative_prompt": (
            "excessive clothing wrinkles, dense hair texture, too many hair strands, busy interior lines, facial over-simplification, "
            "generic face, blocky facial abstraction, messy background, photoreal shading, painterly texture, watercolor, gray wash, "
            "crosshatching, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, "
            "comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture"
        ),
    },
    PromptProfile.variant_c_realism_leaning: {
        "prompt": (
            "naturalistic professional pen-and-ink drawing of the uploaded image, accurate likeness, restrained simplification, "
            "clean contour emphasis, preserved facial identity, preserved natural expression, subtle interior detail, "
            "realistic facial structure, lightly simplified hair, lightly simplified clothing, smooth black ink contours, "
            "polished hand-drawn line illustration on a plain light background"
        ),
        "negative_prompt": (
            "cartoon simplification, exaggerated features, generic face, posterized look, graphic novel style, comic-book inking, "
            "manga style, logo style, stencil effect, excessive black fill, messy background, photoreal shading, painterly texture, "
            "watercolor, gray wash, crosshatching, dense skin texture, sketchy scribbles"
        ),
    },
}


def resolve_generation_prompt(profile: PromptProfile) -> dict[str, str]:
    """Resolve prompt + negative prompt with feature-flag controlled defaults."""
    if profile != PromptProfile.legacy:
        selected = profile
    elif settings.enable_tuned_prompts:
        try:
            selected = PromptProfile(settings.active_tuned_prompt_profile)
        except Exception:
            selected = PromptProfile.balanced_default
    else:
        selected = PromptProfile.legacy

    if selected == PromptProfile.legacy:
        return {
            "prompt_profile": PromptProfile.legacy.value,
            "prompt_version": settings.prompt_registry_version,
            "prompt": LEGACY_PROMPT,
            "negative_prompt": LEGACY_NEGATIVE_PROMPT,
        }

    selected_prompt = PROMPT_REGISTRY[selected]
    return {
        "prompt_profile": selected.value,
        "prompt_version": settings.prompt_registry_version,
        "prompt": selected_prompt["prompt"],
        "negative_prompt": selected_prompt["negative_prompt"],
    }


def _component_stats(binary: list[int], width: int, height: int) -> tuple[int, int]:
    visited = bytearray(len(binary))
    small_components = 0
    total_components = 0
    deltas = (-1, 1, -width, width, -width - 1, -width + 1, width - 1, width + 1)
    for idx, value in enumerate(binary):
        if value != 0 or visited[idx]:
            continue
        total_components += 1
        queue: deque[int] = deque([idx])
        visited[idx] = 1
        size = 0
        while queue:
            cur = queue.popleft()
            size += 1
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
        if size < 40:
            small_components += 1
    return small_components, total_components


def measure_line_diagnostics(path: Path) -> dict[str, float | int | None]:
    img = Image.open(path).convert("L")
    bw = ImageOps.autocontrast(img).point(lambda p: 0 if p < 128 else 255, mode="L")
    width, height = bw.size
    px = list(bw.getdata())
    black_mask = [0 if v < 128 else 255 for v in px]
    black_count = sum(1 for v in black_mask if v == 0)

    # Contour estimate: black pixel that touches white neighborhood.
    contour_count = 0
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if black_mask[idx] != 0:
                continue
            is_contour = False
            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= height:
                    continue
                for nx in (x - 1, x, x + 1):
                    if nx < 0 or nx >= width:
                        continue
                    if nx == x and ny == y:
                        continue
                    if black_mask[ny * width + nx] != 0:
                        is_contour = True
                        break
                if is_contour:
                    break
            if is_contour:
                contour_count += 1

    interior_black = max(black_count - contour_count, 0)
    interior_line_density = round(interior_black / max(width * height, 1), 6)
    small_count, total_components = _component_stats(black_mask, width, height)
    return {
        "small_component_count": int(small_count),
        "component_count": int(total_components),
        "interior_line_density": float(interior_line_density),
        "face_region_density": None,
    }


def score_candidate(diagnostics: dict[str, float | int | None], name: str) -> dict[str, Any]:
    small_components = float(diagnostics.get("small_component_count") or 0.0)
    interior_density = float(diagnostics.get("interior_line_density") or 0.0)
    face_density = diagnostics.get("face_region_density")
    face_penalty = 0.0 if face_density is None else abs(float(face_density) - 0.02) * 50.0

    score = (small_components * 0.8) + (interior_density * 600.0) + face_penalty
    return {
        "candidate": name,
        "score": round(score, 4),
        "penalties": {
            "small_component_penalty": round(small_components * 0.8, 4),
            "interior_density_penalty": round(interior_density * 600.0, 4),
            "face_clarity_penalty": round(face_penalty, 4),
        },
        "diagnostics": diagnostics,
    }
