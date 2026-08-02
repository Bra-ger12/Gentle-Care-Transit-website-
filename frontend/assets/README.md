# Frontend image assets

Static images served by the frontend (referenced with `/assets/...` paths).

## Brand

`LOGO.png` is the supplied master artwork: the house-and-hand icon, the
"Gentle Care Transit" wordmark, and a cream background, on a 2000×2000 canvas.
Nothing renders it directly — the three files below are derived from it, because
the master can't be used as-is:

- its cream background is baked in, so it would sit as a pale box on the navy
  header bar;
- it carries the wordmark, but every brand block in the app already renders the
  name as live text beside the mark, so using it small would print the name twice
  at an unreadable size.

| File | Where it appears | Derived as |
| --- | --- | --- |
| `logo-mark.png` | Every header, sidebar and auth panel (the `.logo-mark` slot) | Icon only, cream keyed to transparent, squared, 512×512 |
| `favicon.png` | Browser tab | The same mark at 64×64 |
| `logo-full.png` | Not currently placed — kept for print, email signatures and social cards | Full lockup, cream keyed to transparent, trimmed to the artwork |

**To change the logo:** replace `LOGO.png` and re-run the derivation, or simply
drop in replacements for `logo-mark.png` and `favicon.png` directly. Nothing
references the mark by any other name, so the change propagates everywhere
without touching markup.

The icon and the wordmark are split on **column height**, not on a gap: the
hand curves to within 18 px of the "G", which is narrower than the gaps between
the letters, so gap-detection picks the wrong boundary and slices "Gentle" into
the mark. Columns taller than 200 px are the icon; every wordmark glyph is under
about 100 px.

## Landing page photos

| File | Where it appears | Suggested crop |
| --- | --- | --- |
| `hero-accessible-van.jpg` | Landing hero (right side) | ~4:3, ≥ 1200 px wide |
| `wheelchair-boarding.jpg` | Full-width photo band (below "How it works") | ~16:9 wide, ≥ 1600 px wide |

Both are wired with graceful fallbacks: if a file is missing, the hero shows its
original dashed placeholder and the photo band hides itself — so the page never
breaks. Drop the files in and reload; no code change needed.

Keep files reasonably sized (ideally < 400 KB each) so the landing page stays fast.
