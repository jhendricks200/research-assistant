---
title: 'Shiori: design system'
source_type: analysis
status: published
topics: [Shiori, Design]
tags: [design system, typography, brand]
entities: [Shiori]
---
# Shiori — Design System

The single source of truth for design decisions on this codebase. The live
tokens are in `app/globals.css`; this file explains what they mean, why they
are what they are, and what is deliberately NOT done. Update this file when a
design decision changes.

## Brand

**Shiori** (栞): bookmark; from *tabi no shiori* (旅のしおり), the little
itinerary booklet Japanese travelers traditionally make before a trip. The
product is a modern tabi no shiori: a Japan trip brief, researched by AI,
reviewed and stamped by a person. Tagline: **"Japan trips, planned properly."**

Feel: a beautifully produced travel dossier. Print materiality, restraint,
one loud element per surface. Premium comes from execution density (type,
hairlines, texture, alignment), never from decoration.

Voice rules:
- NO em dashes anywhere in site copy (founder rule, 2026-07-07). Use a
  comma, colon, or "so"/"and" instead. This includes page titles (use "·").
- Emphasis in display copy = vermilion color at the same weight, never italic.
- Italic = a human speaking (planner sign-off, signature lines, Newsreader
  reading-voice only).
- The founder's name appears at the document sign-off ("[founder name] · your planner"),
  never in marketing hero copy. No inflated claims (no invented counts,
  testimonials, or credentials); honesty about AI's role is part of the brand.

## Palette — "Kachiro" (chosen 2026-06-10, unanimous 4-friend vote)

Warm cream paper with near-black ink and a single vermilion accent; pine
green as the quiet secondary. High contrast on purpose: the earlier softer
ivory palette was rejected as "not powerful."

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#faf7f0` | page background |
| `--paper-deep` | `#efe9dd` | banded sections, panels |
| `--ink` | `#1a1410` | primary text; dark band bg |
| `--ink-soft` | `#5f5546` | secondary text |
| `--line` | `#ddd5c6` | decorative hairlines |
| `--line-strong` | `#857664` | input borders (≥3:1 non-text) |
| `--accent` | `#c0392a` | vermilion; rules, selection |
| `--accent-deep` | `#992b1f` | kickers, links, hover (7.2:1) |
| `--seal` | `#c0392a` | the seal marks |
| `--sage` | `#3e5246` | pine secondary |
| `--sage-deep` | `#2e4034` | numerals, dots, chips text |
| `--sage-soft` | `#e2e7df` | pale chip tint |

All text pairs pass WCAG AA (body 17.05:1, secondary 6.83:1, kicker 7.22:1).
Shadows are rebased on ink: `--shadow-card` / `--shadow-card-hover`.

**Reserved: "Sumi" dark mode** (built ONLY on the concierge chat so far, see 2026-07-07 log entry; rest of the site not yet built). bg `#13100d`, panel
`#1d1916`, text `#f2ede3`, soft `#a89c8a`, accent `#e0492f` (hover lighter
`#e85636`), line `#2c2620` / strong `#6f665a`. The `bg-ink` closing band
inverts to a light band in dark mode (intended anchor). Open idea: brief
pages stay paper-light even in dark mode ("paper glows in a dark room").

## Typography

- **Hanken Grotesk** — display + UI. Loaded via next/font (`--font-hanken`),
  also exposed as `--font-ui` for surfaces where Tailwind weight/tracking
  utilities must compose. Display weights 600–650 with negative tracking:
  `.display-hero` 640 / -0.022em, base `.font-display` 620 / -0.015em,
  `.kicker` 600 / 0.16em uppercase, UI elements 500–600. A grotesque needs
  weight and tight tracking to feel set, not typed.
- **Newsreader** — long-form prose only (ledes, body, `.brief` markdown),
  loaded with `axes: ["opsz"]` so optical sizing works. ALWAYS load the opsz
  axis when a variable font has one; without it, display sizes render the
  text cut blown up (this was a real bug: "the font looks weird").
- Rejected directions (founder taste, see memory): all literary display
  serifs (Fraunces, Playfair, Instrument Serif, Marcellus, Shippori Mincho as
  display); chose refined sans. Shippori Mincho survives ONLY inside seal
  kanji (loaded `preload: false` so Japanese unicode-range slices resolve).

## Marks — the two-seal system

Like Japanese practice: the company has a seal; the person who approves a
document has their own. Never interchangeable.

1. **Brand seal — `components/ShioriSeal.tsx`** (variant "B · deep carve").
   Rounded-square vermilion hanko with a bookmark-ribbon knockout, hand-cut:
   uneven corners, deep off-center notch, two thin carve-break nicks. Exports
   `SEAL_BODY_PATH` / `SEAL_RIBBON_PATH` (48 viewBox) — every consumer
   (header lockup, hero card stamp, loader) renders from these paths, so the
   mark changes in one place. **Favicon exception:** `app/icon.svg` +
   `app/favicon.ico` use a simplified B (nicks omitted — they read as noise
   ≤48px); regenerate the .ico by rendering the SVG large in headless Chrome,
   downscaling via sips, assembling a PNG-ICO.
2. **Personal seal — `components/KeninSeal.tsx`**. Round vermilion seal
   reading **検印** (*kenin*, "inspection seal": the Japanese publishing/QA
   verification stamp — authors stamped copies to certify them). Kanji
   stacked vertically in Shippori Mincho, carved wobbly ring with two groove
   skips. Stamped at ~40px, rotated ~2.5deg, multiply blend, beside the
   planner sign-off on every brief. Meaning: *a person inspected this one.*
3. **Ribbon — `components/ShioriRibbon.tsx`** (variant E). The bare carved
   bookmark ribbon, two path variants: `mark` (the compact glyph) and
   `hanging` (an elongated tail with a flat top cut, drawn as its own path so
   the notch never distorts — never non-uniformly scale `mark`). Placement
   rule: **the ribbon hangs over the top edge of page-like surfaces**, the
   way a marker ribbon hangs out of a closed book — flush with (or peeking
   above) the edge, tail descending onto the surface, in the right third of
   the width, never centered, never in the corner gutter. Never used as a
   logo repeat. Current placements: the brief page masthead (44px mobile /
   64px ≥sm, `right-[21%]` of the content column, multiply blend + faint
   drop shadow so it sits ON the paper) and the hero sample-brief card (38px
   at `left-[74%]`, top 5px above the card border, inside the rotated link
   so it rides the hover-straighten; NOT multiply-blended there — the tail
   crosses the photo and blending sank it into dark foliage). Divider usage:
   the `mark` variant remains the `.brief-hr` section divider (22px ribbon
   at full ink, flanked by short hairlines that fade at their outer ends),
   kept because it appears at most once or twice per document and rhymes
   with the masthead bookmark rather than repeating it. Keep it rare.
4. **Textured display stamp — `public/brand/seal-stamp.png`**. Generated
   procedurally by `scripts/generate-seal-stamp.py` FROM the live
   `SEAL_BODY_PATH`/`SEAL_RIBBON_PATH` exports, with a stamped-ink treatment
   (speckle, grain, eroded edges) matched numerically to the original
   founder-supplied art (kept as `source-original.png`). Used where texture
   reads large: the OG share card (`app/opengraph-image.tsx`) and the social
   avatars (`avatar-*-800.png`, composited from the stamp at 62% width,
   safe-circle centered). Re-run the script after any seal-geometry change so
   the family never drifts. Details in `public/brand/README.md`.

## Motion — the seal "line boil"

The loading mark (`components/SealLoader.tsx`, exports `SealLoader` +
`BoilingSeal`) animates with a **line boil** — the classic hand-drawn
animation technique (think vintage cartoons and modern Anthropic-style logo
bumpers) where the same drawing is redrawn a handful of times and the frames
are flipped through, making the lines shimmer alive without anything moving.

Implementation is a literal **flipbook**: eight pre-rendered frames of the
seal, each displaced by a fixed-seed fractal noise field (`BOIL_SEEDS`, no
adjacent repeats), flipped at **6 fps** (`BOIL_FPS`; 8 read as too busy) by
toggling `display` between sibling groups from one rAF loop. The ribbon rides
a 1.6x stronger displacement than the body (it is the paper strip).

**Hard-won browser lesson — do not regress this:** do NOT animate SVG filter
primitives. SMIL `<animate>` on feTurbulence froze after first paint in
Chrome (timeline advanced, filter never re-rendered), and rAF-rewriting
filter attributes froze in at least one other engine. Toggling element
visibility repaints in every engine; each frame's filter rasterizes once and
is cached. `prefers-reduced-motion` renders the static seal (matchMedia gate
via useSyncExternalStore; CSS cannot stop SMIL/JS loops).

Used in: form submit pending state (18px, paper-colored via `--seal`
override on the dark button — vermilion fails contrast there),
`app/loading.tsx` route fallback (56px + "Preparing…"), and the intake
post-submission overlay: a **full-viewport takeover** (fixed `inset-0`,
`bg-paper/70` + `backdrop-blur-md`, page blurred behind, scroll locked) with
only the 68px boiling seal over the "Shiori" wordmark centered — no card, no
border, a deliberate blank moment. It holds ~4.5s after the action resolves,
then fades out (700ms opacity) to reveal the success message already sitting
in the page flow where the form was: plain centered text (static seal +
heading + one paragraph), no card border — the box read weaker than open
paper. Focus moves to the success heading once the overlay clears. Reduced
motion never mounts the overlay (no flash): static seal + message render
immediately. The body grain overlay (z-60) intentionally sits above the
overlay (z-50), so the takeover keeps the paper texture.

## Materiality & layout

- Paper grain: body::before fixed overlay, feTurbulence SVG data-URI at 3%
  opacity, multiply. Visible if you look, invisible if you don't.
- `.plate`: filmic photo frames (3px radius, vignette + grain) for all
  photography. Photos are the landing page's emotional engine — the hero's
  brief-as-artifact card (rotated sheet stack, straightens on hover) is the
  conversion asset and must stay above the fold at 1280x800.
- Radius scale: pill (buttons) / `--radius-card` 10px / `--radius-chip` 4px.
  One layered card shadow + hover variant. No other radii or shadows.
- Whitespace must frame something dense; numerals/rules anchor every tall
  band. Hairline-ruled structures (Promise triad, trust row) over boxes.

## Page inventory

Landing (`/`): SiteHeader (seal+wordmark lockup, pill CTA) → Hero (headline
with vermilion emphasis, brief-artifact card stamped bottom-corner) → Promise
triad → HowItWorks (numeral+rule+title line) → ClosingCta (dark band,
signature line) → SiteFooter (wordmark + 栞 story line). Intake (`/intake`):
4 steps, mode fork (scratch / sharpen), Japan-specific placeholders. Brief
(`/trip/[slug]`): markdown dossier, plates, ribbon dividers, kenin-stamped
sign-off, "Drafted with AI research, reviewed and signed by a person."
Contact (`/contact`, 2026-07-07): lede → poster mailto (fluid
clamp(1.6rem,6.5vw,3rem), domain in vermilion, whitespace-nowrap so it never
wraps mid-word) → hairline triad (before booking / mid-planning / mid-trip)
→ kenin sign-off ("[founder name], your planner", static seal, brief-idiom treatment);
linked from the landing footer. Dev-only: `/logo` (identity review page —
REMOVE before public launch).

## Decision log

- 2026-06-10 — Design audit: hero artifact, whitespace compression, depth
  pass, action layer. Fonts: Fraunces → Hanken Grotesk (serif round rejected
  whole). Brand: Occasion → Shiori. Two-seal identity, hanko motif.
- 2026-06-10 — Palette: Kachiro beats Hinomaru (white/flag-red) and Sumi
  (dark) in a 4-friend unanimous vote; Sumi reserved for dark mode.
- 2026-06-11 — Loader: stamp-press motion rejected → paper wave → final
  **line-boil flipbook** (browser bugs forced the technique; it also matches
  the founder's reference best). 8 frames, 6 fps. Kenin seal approved (検印
  over name katakana). Mark B promoted site-wide; ribbon E becomes the brief
  divider.
- 2026-06-11 — Ribbon promoted from divider-only ("super weak") to the
  hanging-bookmark placement: a `hanging` elongated variant hangs over the
  top edge of the brief page and the hero sample-brief card. Divider kept.
- 2026-06-11 — Brief divider strengthened (founder: bookmark "looks very
  weak"): ribbon 15px/80% opacity → 22px/full ink; flanking hairlines fade
  at their outer ends and sit closer (gap 1.1rem → 0.9rem). Still rare.
- 2026-06-11 — "How it unfolds" redesigned as **stamped slips** (founder:
  section "seems kind of weak... should be hard hitting"): four paper slips
  on the paper-deep desk, slightly rotated/offset, boxed tilted vermilion
  number stamps (border-4, text-3xl, multiply), dashed route line behind on
  lg, kenin seal on step 03. Chosen over "ledger" (editorial scale) and
  "ink band" (second dark band would fight the closing CTA anchor); stamps
  sized to stay ON the slip per founder. Copy went verb-first: Hand it
  over / AI goes wide / [founder name] knows Japan / You book it ("[founder name] knows Japan"
  picked from an 8-option language wall; a deliberate, allowed expertise
  claim, not a biography/credential count).
- 2026-06-11 — Slips route line upgraded to the **mizuhiki thread**: a 2px
  continuous vermilion cord (#c0392a, 0.85 opacity) sagging between the
  slips, referencing mizuhiki gift cords and akai ito (red thread of fate).
  Founder chose the knotless version over knotted (overhand/awaji/bow/
  double-coin studies) and ink-toned variants — knots read as ambiguous
  marks at thread scale ("people might not realize those are knots").
  2px is the ceiling: any heavier and it fights the stamps for the
  section's one loud element. Desktop (lg) only.
- 2026-06-11 — Thread given an **arrival boil**: the SealLoader flipbook
  technique (8 fixed-seed turbulence frames, display-toggled at 6 fps)
  runs for 5s after the section first scrolls into view (threshold 0.4),
  then settles onto the clean path. Founder chose 5s over 3s; persistent
  boil rejected as too much motion beside readable text. Reduced motion,
  SSR, and no-JS all render the still thread. Lives in
  components/landing/HowItWorks.tsx (now a client component).
- 2026-06-12 — Mobile (single-column) thread: a straight 2px vermilion
  segment centered in each gap between stacked slips, spanning exactly the
  2rem gap with 1.5px end insets so it never crosses onto the paper.
  Founder iterated: weaving offsets → centered hanging → straight ("the
  stack's spine"). Deliberately still (no boil): the section enters a
  phone viewport in pieces, so there is no clean arrival beat, and motion
  during active scrolling irritates. sm (2-col) gets no connector by
  design; shimenawa was proposed and rejected on meaning (sacred boundary
  rope, not a connector — see 2026-06-12 discussion; mizuhiki = connection
  is the correct symbol).
- 2026-06-12 — Mobile arrival animations (mobile ONLY; desktop keeps the
  thread boil as its single flourish): (1) each spine segment draws in
  (0.35s stroke-dashoffset) when its gap scrolls into view; (2) each
  number stamp line-boils for 12 frames (~2s) at displacement scale 4 on
  arrival, then settles — stamp rendered as an SVG twin (MobileBoilStamp,
  sm:hidden) because filters on HTML are unreliable; the HTML stamp shows
  at sm+. Rejected on the way: smooth CSS press ("happens so quick"),
  stepped 6fps flipbook slam with squash/rebound ("bouncing up and down")
  and without ("don't like how it looks"), ink-bleed blur, box draw-on.
  Founder picked pure boil, strength tuned 2.6 → 5 ("too subtle"/"tiny
  bit too aggressive") → 4. Reduced motion: everything still.
- 2026-06-11 — Intake success: the /thank-you redirect replaced by an
  in-place branded interstitial (68px boiling seal + wordmark, 4.5s hold,
  cross-fade into the success message inside the form card).
- 2026-07-07 — Concierge chat (`components/ConciergeChat.tsx`): styled as
  "the booklet talking" — assistant replies are open Newsreader prose on
  paper marked by a short 22x2px vermilion rule (no bubble); traveler
  messages are ink slips (card radius with one chip-radius corner); hanging
  ribbon over the conversation's top edge at right-[21%]; BoilingSeal 18px
  as the thinking mark; sage-soft suggestion chips. First Sumi dark-mode
  surface, scoped via `prefers-color-scheme` overrides on `.cg-root`
  (travelers chat at night): ink slips invert to light per the anchor rule,
  ribbon drops multiply blend in dark (multiply dies on near-black).
  Founder reviewed the reserved Sumi set live and asked for LESS contrast;
  the chat now runs a softened Sumi (founder-approved direction, tokens
  PROVISIONAL for site-wide use): paper `#171310`, panel `#211c17`, ink
  `#ded4c2`, soft `#988c79`, accent/seal `#cf4830` (hover `#d95a3e`), line
  `#2e2823` / strong `#665d51`, sage-soft `#232b25`, sage-deep `#a3b3a6`.
  If dark mode spreads beyond the chat, start from these, not the original
  reserved values.
- 2026-07-07 — Concierge chat interaction polish (founder-reviewed live):
  theme toggle in the masthead (sun/moon, 44px, follows system until an
  explicit pick, persisted per device via localStorage); conversation
  persisted per trip token (saved between turns only, never mid-stream);
  touch targets normalized to 44-46px, Send matches the 46px input height;
  honesty hint shows on the empty state only, 12px; assistant prose capped
  at 60ch; Send lights vermilion (`--accent`, cream text pinned both
  themes, `--accent-deep` hover) when the input has text; input caret
  vermilion; and an **input light-sweep**: after a 450ms typing pause, a
  bright band (light `#c9b898` / dark `#fffdf5`, 30-70% gradient stops)
  sweeps through the typed glyphs twice at 1.7s per pass
  (background-clip: text two-layer trick — the field's own background MUST
  live in the `.cg-input` class, not inline style, or the clipped gradient
  is overridden and the text turns invisible). Founder tuned: subtle →
  brighter/wider → slowed 1.1s → 1.7s. The same sweep also runs on the
  just-sent user slip while the reply is pending ("being read": up to 3
  passes, released the moment the first token streams in) — slip background
  moved to a `.cg-slip` class for the same inline-override reason; the
  slip's band is darker-than-text (light `#c2b295`, dark `#6d5f4b`) since
  the slip's text is the light element. Reduced motion disables the sweep,
  the caret blink, and message rise.
- 2026-06-11 — Interstitial pulled out of the form card (founder: no box):
  now a full-viewport blurred overlay (`bg-paper/70` + `backdrop-blur-md`,
  scroll locked, seal + wordmark only), fading out to a settled success state
  that is plain centered text in the page flow — card border dropped there
  too; the form's page heading frames it better than a box.

- 2026-09-05 — Local site review: shortened hero with pricing and sample CTA;
  two-column service comparison below the hero; mobile secondary navigation
  stays visible. Contact fields move to intake step 4, with error routing kept
  in sync. Teardown input comes directly after a short lead. Guide teaser is
  explicitly a screenshot, with the $59 add-on price beside its CTA. Sample
  has section links, accurate 2026 weekdays, unconfirmed booking labels,
  illustrative-budget disclosure, a Kansai departure, and an official booking
  link. About uses existing biography and a labeled planning illustration;
  no new portrait or credentials were invented. Review locally before push.
