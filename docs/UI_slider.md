The previous prompt already established the style-profile product direction. This task is specifically to implement the UI and request wiring for that existing design: add a 3-position style slider (Realistic, Balanced, Stylized), default to Balanced, send the selected preset in the generation request, and map it to the existing backend prompt profiles.


CODING AGENT HANDOFF: UI UPDATE FOR STYLE SLIDER MAPPED TO INTERNAL VARIANTS

Objective
Update the user-facing UI so users can control the output style with a simple slider instead of thinking about prompts or pipeline settings.

The UI control should express:
- more realistic / more faithful
to
- more stylized / more polished

This is a UX abstraction over the internal prompt profiles we already implemented.

Do not expose:
- prompt text
- threshold settings
- cleanup settings
- vectorization settings
- morphology
- min component size
- denoise strength
- CFG
- any internal tuning language

The user should only see a clear style control.

Product behavior
The slider is a UI control that maps to discrete internal profiles, not a true continuous backend interpolation.

Initial mapping:
- left = `realistic_seed`
- middle = `balanced_default`
- right = `stylized_seed_do_not_default`

Important note
The current “stylized” profile is only a seed and may still be too aggressive.
If it is not production-ready, still wire the slider structurally, but either:
1. map the rightmost position temporarily to a moderated stylized profile if available, or
2. disable the far-right position in the UI with a “coming soon” treatment, or
3. map it to `balanced_default` behind the scenes until the stylized profile is ready

Preferred approach:
- implement the full 3-position slider API contract now
- allow the backend to decide whether `stylized` is available
- if unavailable, show the position but make it visually disabled or labeled “Beta” / “Soon”

UI requirements

Primary control
Add a style slider with exactly 3 labeled positions:
- Realistic
- Balanced
- Stylized

Default selection:
- Balanced

Helper text under the slider:
- “Choose how closely the result follows the original versus a cleaner illustrated look.”

Alternative shorter helper text if needed:
- “Move toward faithful detail or cleaner illustration.”

Behavior
- Slider snaps to the 3 discrete positions
- No freeform continuous values in v1
- Changing the slider updates the current selected style profile in state
- The selected style profile is included in the generation request payload
- Existing generation flow should continue to work with no other user-visible complexity

Internal mapping contract
Map the slider positions to these backend profile identifiers:

- Realistic -> `realistic_seed`
- Balanced -> `balanced_default`
- Stylized -> `stylized_seed_do_not_default`

If product/API naming needs to be cleaner for production, you may alias them in UI payloads as:
- `realistic`
- `balanced`
- `stylized`

But maintain a clear backend mapping to the implemented profiles.

Frontend implementation guidance

State
Add a style selection state field, e.g.:
- `styleProfile`
or
- `stylePreset`

Default value:
- `balanced`

Accepted values:
- `realistic`
- `balanced`
- `stylized`

Component behavior
Implement a segmented slider or 3-stop range control that:
- clearly shows the current selected mode
- is easy to use on desktop and mobile
- visually communicates the left-to-right tradeoff
- keeps the design simple and product-like

Recommended labels:
- Left: Realistic
- Center: Balanced
- Right: Stylized

Recommended caption:
- “Style”

Optional descriptive text per selected mode
When the user changes the selection, show a short one-line description:

For Realistic:
- “Keeps more of the original structure and detail.”

For Balanced:
- “Best mix of faithfulness and polished line art.”

For Stylized:
- “Pushes toward a cleaner, more illustrated look.”

If Stylized is not ready:
- “More illustrated look. Coming soon.”
or
- “More illustrated look. Beta.”

Preview and UX behavior
- If there is a result preview area, display the currently selected style label near the Generate button or result card
- If the user changes the slider after upload but before generation, the new style should apply to the next run
- If the user changes the slider after a result already exists, do not silently regenerate; require an explicit Generate / Regenerate action

Request payload contract
Include the selected style in the generation request, for example:
{
  "stylePreset": "balanced"
}

Backend mapping expectation:
- `realistic` -> `realistic_seed`
- `balanced` -> `balanced_default`
- `stylized` -> `stylized_seed_do_not_default`

If the backend currently expects raw internal profile names, that is acceptable for now, but keep the UI layer clean and user-friendly.

Backend requirements
Update the request handling so the style preset selects the prompt profile before generation begins.

Pseudo-logic:
- if stylePreset == "realistic": use `realistic_seed`
- else if stylePreset == "balanced": use `balanced_default`
- else if stylePreset == "stylized": use `stylized_seed_do_not_default`
- else default to `balanced_default`

If stylized is disabled in configuration:
- either reject with a safe fallback to balanced
- or return capability metadata so the UI can disable that option

Preferred backend capability contract
Expose available style presets from backend config, e.g.:
{
  "availableStylePresets": ["realistic", "balanced"],
  "defaultStylePreset": "balanced"
}

Then UI behavior should be:
- show all three positions if desired for roadmap clarity, but disable unavailable ones
or
- only enable the presets returned by backend capabilities

Preferred UX if backend capabilities exist
- Realistic: enabled
- Balanced: enabled
- Stylized: disabled with “Beta” or “Soon” if unavailable

Do not overengineer
Do not add:
- multiple advanced panels
- direct prompt editing
- internal parameter controls
- observability or developer controls in the main user flow

This is a simple user-facing abstraction layer.

Acceptance criteria

UI
- A visible style control exists with 3 labeled positions: Realistic, Balanced, Stylized
- Balanced is selected by default
- The user can change styles before generation
- The selected style is clearly visible

Behavior
- The selected style is sent in the request payload
- Backend maps it to the correct prompt profile
- If Stylized is unavailable, the UI handles that gracefully without breaking the flow
- Existing generation behavior remains stable

Copy
Use these exact labels unless there is a strong design reason to shorten them:
- Style
- Realistic
- Balanced
- Stylized

Use this helper text:
- “Choose how closely the result follows the original versus a cleaner illustrated look.”

Optional future extension
Structure the component so it can later support 5 positions without a rewrite, but only ship 3 positions now.

The future 5-position mapping could become:
- Very Realistic
- Realistic
- Balanced
- Polished
- Stylized

Do not implement 5 positions now.
Only keep the component architecture flexible enough to support it later.

Deliverables expected
- updated UI with the 3-position style slider
- request payload including selected style preset
- backend mapping from UI style preset to internal prompt profile
- graceful handling for unavailable stylized mode