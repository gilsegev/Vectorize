Coding agent tuning brief

Goal: move outputs from “good generated line art” to “clean professional pen interpretation.”

Do not push toward cartoon, comic, or highly stylized engraving.
Do not maximize detail retention.
Optimize for the feeling that a skilled illustrator chose only the necessary lines.

Quality target

The output should:

preserve identity and expression
simplify hair, fabric, and skin detail
keep strong contours and readable silhouettes
reduce incidental interior lines
look hand-edited and intentional
avoid noisy texture, crosshatching, and busy micro-detail
Main failure modes to reduce
too many hair strands
too many shirt and sleeve folds
too many small facial marks around cheeks, eyes, and smile lines
inconsistent simplification across subjects
linework that feels traced rather than interpreted
Prompt tuning instructions

Use prompts that bias toward restrained pen drawing rather than “vector art” or “comic ink.”
The word “vector” can sometimes push the model toward generic clipart or posterized outputs. Use it sparingly.

Base positive prompt

Use this as the starting point:

clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved facial identity, preserved natural expression, selective line placement, clean silhouettes, minimal but confident facial features, minimal fabric folds, reduced hair strand detail, smooth black ink lines on plain light background, hand-drawn editorial illustration quality
Base negative prompt

Use this as the starting point:

messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, too many fabric folds, excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture
Stronger “polish” prompt variant

Use this when outputs are still too busy:

clean professional pen illustration, highly selective linework, only essential contours and facial features, simplified hair masses instead of individual strands, simplified clothing with only major folds, elegant black ink contours, quiet interior detail, natural human likeness, readable expression, polished hand-drawn look, minimal line clutter, premium editorial line art

Negative prompt:

busy linework, scratchy pen marks, excess texture, too many contour lines, too many smile lines, too much cheek detail, too many eyelid lines, detailed skin texture, dense hair texture, dense clothing wrinkles, comic inking, stylized cartoon features, dramatic graphic-novel shading, hatch marks, stippling, rough sketch
Less stylized realism-preserving prompt variant

Use this when outputs become too abstract or too “designed”:

naturalistic pen-and-ink portrait drawing, accurate likeness, restrained simplification, clean contour emphasis, minimal shading, subtle interior detail, realistic proportions, natural facial structure, lightly simplified hair and clothing, polished black line drawing

Negative prompt:

cartoon simplification, exaggerated features, icon-like face, overly flat shapes, posterized look, logo style, stencil effect, aggressive abstraction
Prompting rules for the agent
Favor phrases like:
restrained linework
selective line placement
simplified interior detail
preserved facial identity
natural expression
minimal fabric folds
simplified hair masses
polished hand-drawn look
professional pen illustration
Avoid overusing phrases like:
vector art
comic style
coloring book
logo
stencil
engraving
tattoo flash

These tend to push the model in the wrong direction.

When faces are weak, add:
clean minimal facial lines, preserved expression, preserved likeness, avoid extra cheek and eye detail
When hair is too noisy, add:
hair represented as simple flowing masses, reduced strand detail, no dense hair texture
When clothing is too busy, add:
only major garment folds, simplified sleeves and collars, no unnecessary wrinkle detail
Parameter tuning instructions

The coding agent should test prompt changes before rewriting cleanup logic.

Generation settings guidance

Use these as directional tuning rules, not hard requirements.

If output is too noisy or too detailed
lower denoise strength slightly
reduce CFG slightly if the model is overcommitting to stylized line patterns
strengthen negative prompt against texture and folds
prefer fewer variants with tighter prompts over many loose variants
If output is too flat or loses identity
slightly increase denoise strength
add “preserved facial identity” and “natural human likeness”
weaken negative prompt terms that suppress all facial detail
If output gets too stylized
remove terms like “editorial” or “illustration quality” only if they are causing stylization drift
add “naturalistic” and “accurate likeness”
explicitly negative-prompt cartoon/comic/manga/graphic novel
Candidate selection instructions

If generating multiple candidates, select the candidate with:

the cleanest face simplification
the least unnecessary hair texture
the fewest unnecessary clothing folds
the strongest readable silhouette
the most consistent treatment across all people in the image

Reject candidates that:

add lots of interior micro-lines
overdefine cheeks, eyelids, or smile lines
create scratchy hair texture
produce comic-book style shadows
make one face much more simplified than the others
Cleanup tuning instructions

The cleanup stage should support the prompt, not fight it.

Tell the agent to tune cleanup toward:

removing tiny isolated interior blobs
removing very short stray strokes
preserving long contour lines
preserving mouth, eye, jawline, hand outline, and silhouette
lightly suppressing dense interior texture

Do not aggressively thin or simplify to the point that faces lose expression.

Specific cleanup goal

Prefer:

fewer interior marks
cleaner negative space
more stable outer contours

Over:

maximum detail retention
A/B tuning loop for the agent

Run tuning in this order:

Round 1

Change prompts only. Keep cleanup fixed.

Test:

current prompt
base professional pen prompt
stronger polish prompt
realism-preserving prompt

Evaluate:

face cleanliness
hair simplification
clothing simplification
identity preservation
Round 2

Keep the best prompt. Tune cleanup lightly.

Adjust only:

threshold sensitivity
minimum connected component size
mild morphology for speck reduction

Do not change multiple cleanup knobs at once.

Round 3

Add lightweight candidate scoring.

Prefer candidates with:

lower interior line density
lower small-component count
better face clarity by visual review
Exact instruction block you can paste to the coding agent
Tune the generation prompts toward clean professional pen-and-ink interpretation, not cartoon or comic stylization.

Primary objective:
Produce outputs that look like a skilled illustrator simplified the photo by hand using black ink.

Optimize for:
- preserved likeness
- preserved natural expression
- restrained linework
- strong outer contours
- simplified interior detail
- reduced hair strand detail
- reduced fabric fold detail
- minimal but readable facial features
- clean negative space
- consistent treatment across all subjects

Avoid:
- comic-book style
- manga/cartoon features
- crosshatching
- engraving texture
- scratchy sketch lines
- noisy micro-detail
- realistic skin texture
- excessive wrinkles and folds
- dense hair texture
- over-detailed cheek and eye lines

Start from this positive prompt:
'clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved facial identity, preserved natural expression, selective line placement, clean silhouettes, minimal but confident facial features, minimal fabric folds, reduced hair strand detail, smooth black ink lines on plain light background, hand-drawn editorial illustration quality'

Start from this negative prompt:
'messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, too many fabric folds, excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture'

Run 3 to 4 variants and select the one with:
1. cleanest facial simplification
2. least unnecessary hair texture
3. least unnecessary clothing detail
4. strongest silhouette
5. most consistent simplification across all people

Only after prompt tuning, lightly tune cleanup to remove tiny isolated marks and short stray interior strokes while preserving facial expression and primary contours.