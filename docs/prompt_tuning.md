CODING AGENT HANDOFF: UPDATED PROMPT BASELINE AND STYLE PROFILE DIRECTION

Context
- The latest comparison round indicates that `Variant A` performed best overall.
- `Variant A` improves on the prior baseline by preserving subject identity cues better while maintaining nearly the same polish level.
- `Control (Base)` remains strong and should be kept as a fallback baseline.
- `Variant C` is useful as the seed for a more realistic / more faithful mode.
- `Variant B` is too aggressive for default use. It over-simplifies and loses too much subject-specific character.

Conclusion
- Promote `Variant A` to the new default prompt profile.
- Keep cleanup and vectorization unchanged for now.
- Treat prompt/profile selection as the primary quality lever.
- Do not spend more effort on cleanup micro-tuning until profile behavior is validated on a broader subject set.

Primary quality target
Produce outputs that feel like a skilled illustrator created a clean professional pen-and-ink interpretation of the uploaded image.

The output should:
- preserve defining subject identity cues
- preserve important structural features
- simplify incidental detail
- reduce low-value texture and unnecessary interior lines
- keep strong contours and readable silhouettes
- avoid looking like clipart, comic art, stencil art, or a traced filter
- look polished, selective, and intentional

Optimize for the balance point between:
- faithfulness to the source
- professional simplification and polish

Do not optimize for:
- maximum realism
- maximum simplification
- dramatic graphic stylization

New default profile
Name: `balanced_default`
Source lineage: based on former `Variant A`

Positive prompt:
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved subject identity cues, preserved distinctive structural features, natural proportions, selective line placement, clean silhouettes, minimal but distinctive key features, lightly simplified texture and surface detail, smooth black ink lines on plain light background, polished hand-drawn illustration

Negative prompt:
generic simplification, overly idealized structure, blocky massing, posterized structure, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive texture, too many interior lines, noisy micro-detail, cluttered low-value detail, sketchy scribbles, duplicated features, deformed structure, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture

Why this is now the default
- It preserved subject-defining cues better than the previous base control.
- It maintained strong polish without drifting into generic abstraction.
- It kept the best balance between recognizability and professional simplification.
- It is currently the best candidate for the generic product default, pending broader subject validation.

Fallback profile
Name: `balanced_fallback_base_control`
Source lineage: former `Control (Base)`

Positive prompt:
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved subject identity cues, preserved important structural features, selective line placement, clean silhouettes, minimal but confident key features, reduced low-value texture, smooth black ink lines on plain light background, hand-drawn editorial illustration quality

Negative prompt:
messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive texture, too many interior lines, noisy micro-detail, cluttered low-value detail, sketchy scribbles, duplicated features, deformed structure, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture

When to use fallback
- If the new default behaves inconsistently on non-human subjects
- If a test image shows the default becoming too soft or too structurally interpretive
- If a slightly more conservative balanced mode is needed

Realistic profile seed
Name: `realistic_seed`
Source lineage: former `Variant C`

Positive prompt:
naturalistic professional pen-and-ink drawing of the uploaded image, accurate structure, restrained simplification, clean contour emphasis, preserved subject identity cues, preserved important structural features, subtle interior detail, natural proportions, lightly simplified texture, smooth black ink contours, polished hand-drawn line illustration on a plain light background

Negative prompt:
cartoon simplification, exaggerated features, generic structure, posterized look, graphic novel style, comic-book inking, manga style, logo style, stencil effect, excessive black fill, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, dense texture, sketchy scribbles

How to use this profile
- Treat as the starting point for the “Realistic” end of the future style control
- Use when a more faithful interpretation is preferred
- Not the default unless broader testing shows it generalizes better

Stylized profile seed
Name: `stylized_seed_do_not_default`
Source lineage: former `Variant B`

Positive prompt:
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserve subject identity cues, preserve distinctive structural features, simplify texture to major forms only, simplify secondary surfaces and interior details, selective line placement, clean silhouettes, minimal but readable key features, polished hand-drawn editorial line art on a plain light background

Negative prompt:
excessive texture, dense surface detail, too many interior lines, busy linework, over-simplification of defining features, generic structure, blocky abstraction, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, sketchy scribbles, duplicated features, deformed structure, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture

Important note on stylized seed
- This prompt direction is too aggressive for default use.
- It tends to flatten subject-specific character.
- Keep only as a seed for a future “Stylized” mode after moderation and retesting.

Implementation guidance
- Keep generation, cleanup, and vectorization parameters fixed for now.
- Promote prompt/profile selection as the main tuning mechanism.
- Do not perform new cleanup sweeps unless a prompt profile clearly reveals a consistent downstream weakness.

Style control direction
The product should eventually expose a user-facing control that maps between:
- more realistic / more faithful
- more balanced / default
- more stylized / more polished

Recommended internal profiles
1. `realistic_seed`
2. `balanced_default`
3. `stylized_seed_do_not_default`

Important implementation note
- Do not implement a truly continuous backend slider first.
- Map UI slider ranges onto discrete internal profiles.
- Start with 3 positions:
  - Realistic
  - Balanced
  - Stylized

Validation requirement before locking defaults
The current winning result was selected on a people-centric input.
Before finalizing the generic app behavior, validate the three-profile system on a broader subject set including:
- a pet
- a vehicle
- a building
- a consumer product/object
- a logo or graphic mark

Evaluation criteria for broader validation
Judge each profile on:
1. preservation of defining subject identity cues
2. preservation of important structural features
3. simplification quality
4. texture reduction quality
5. line clarity
6. overall polish
7. whether it feels intentionally drawn rather than mechanically processed

Decision rules going forward
- Default to `balanced_default`
- Fall back to `balanced_fallback_base_control` if default performance is unstable on certain subject classes
- Use `realistic_seed` as the basis for the faithful end of the style control
- Do not expose the stylized profile by default until it has been moderated and validated

Expected next deliverable from the agent
- implement the new default prompt as `balanced_default`
- preserve the previous base as fallback
- define internal profile objects for `realistic_seed`, `balanced_default`, and `stylized_seed_do_not_default`
- run broader validation on non-human subject classes before shipping profile behavior as stable