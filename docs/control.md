Control

Use current r1_base_prof_pen unchanged as the control.

Positive prompt
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved facial identity, preserved natural expression, selective line placement, clean silhouettes, minimal but confident facial features, minimal fabric folds, reduced hair strand detail, smooth black ink lines on plain light background, hand-drawn editorial illustration quality
Negative prompt
messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, too many fabric folds, excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture
Variant A: preserve likeness more strongly

Use this to keep the same overall polish but pull back from generic face abstraction.

Goal
preserve adult facial individuality
preserve natural human specificity
reduce the risk of “clean but generic”
Positive prompt
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserved facial identity, preserved adult facial individuality, preserved natural expression, natural facial structure, selective line placement, clean silhouettes, minimal but distinctive facial features, lightly simplified hair and clothing, smooth black ink lines on plain light background, polished hand-drawn illustration
Negative prompt
generic face simplification, overly idealized face, blocky hair masses, posterized facial structure, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, excessive wrinkles, too many fabric folds, excessive hair strands, noisy micro-detail, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, cluttered interior lines, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture
What this variant is testing
whether likeness can improve without giving back too much clutter
whether the father’s face stays more human-specific
whether hair stays simplified without becoming a solid graphic block
Variant B: selective simplification

Use this to simplify clothing and hair harder while explicitly protecting faces.

Goal
suppress low-value detail in fabric and hair
keep facial cues more intact
move toward “illustrator chose what mattered”
Positive prompt
clean professional pen-and-ink line drawing of the uploaded image, restrained linework, strong outer contours, simplified interior detail, preserve facial identity and expression, preserve distinctive facial cues, simplify clothing to major folds only, simplify hair into clean flowing masses with limited strand detail, selective line placement, clean silhouettes, minimal but readable facial features, polished hand-drawn editorial line art on a plain light background
Negative prompt
excessive clothing wrinkles, dense hair texture, too many hair strands, busy interior lines, facial over-simplification, generic face, blocky facial abstraction, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, skin texture, pores, realistic shading, sketchy scribbles, duplicated features, deformed hands, comic-book exaggeration, cartoon style, manga style, engraving texture, woodcut texture
What this variant is testing
whether you can hold the current polish while reducing shirt/hair clutter further
whether face quality survives stronger simplification in non-face regions
Variant C: realism-leaning pen interpretation

Use this as the “closer to original person” side of the future slider.

Goal
keep the professional pen look
allow slightly more human specificity
avoid drifting into stylized poster art
Positive prompt
naturalistic professional pen-and-ink drawing of the uploaded image, accurate likeness, restrained simplification, clean contour emphasis, preserved facial identity, preserved natural expression, subtle interior detail, realistic facial structure, lightly simplified hair, lightly simplified clothing, smooth black ink contours, polished hand-drawn line illustration on a plain light background
Negative prompt
cartoon simplification, exaggerated features, generic face, posterized look, graphic novel style, comic-book inking, manga style, logo style, stencil effect, excessive black fill, messy background, photoreal shading, painterly texture, watercolor, gray wash, crosshatching, dense skin texture, sketchy scribbles
What this variant is testing
whether a slightly more realistic line-art mode feels better for family photos
whether users might prefer this over the more polished editorial mode
Agent instructions for running the next round

Use:

r1_base_prof_pen as the control
Variant A
Variant B
Variant C

Keep everything else fixed:

same input
same generation model
same number of variants
same cleanup parameters
same vectorization settings

Do not change cleanup or vectorization in this round.

Evaluate outputs on:

facial likeness preservation
facial warmth and naturalism
hair simplification quality
clothing simplification quality
overall polish
whether the result feels “drawn by a pro” rather than “processed by a filter”