from app.models import JobSettings, PromptProfile
from app.services.tuning import resolve_generation_prompt, score_candidate


def test_prompt_profile_resolution_uses_requested_profile():
    payload = resolve_generation_prompt(PromptProfile.stronger_polish)
    assert payload["prompt_profile"] == "stronger_polish"
    assert "selective linework" in payload["prompt"]
    assert "busy linework" in payload["negative_prompt"]


def test_cleanup_knobs_validate_ranges():
    settings = JobSettings(
        cleanup_threshold_bias=8,
        cleanup_min_component_px=120,
        cleanup_speck_morph=1,
    )
    assert settings.cleanup_threshold_bias == 8
    assert settings.cleanup_min_component_px == 120
    assert settings.cleanup_speck_morph == 1


def test_candidate_scoring_is_deterministic():
    diagnostics = {
        "small_component_count": 12,
        "interior_line_density": 0.015,
        "face_region_density": None,
    }
    a = score_candidate(diagnostics, "candidate_1.png")
    b = score_candidate(diagnostics, "candidate_1.png")
    assert a["score"] == b["score"]
    assert a["penalties"] == b["penalties"]
