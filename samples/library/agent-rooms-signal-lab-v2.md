---
title: 'Agent Rooms: Signal Lab v2 changes'
source_type: analysis
status: published
topics: [Agent Rooms, Design]
tags: [design system, handoff]
entities: [Signal Lab]
---
# Signal Lab v2 - what changed, and what the handoff got wrong

Measured from the inline styles of `Signal Lab Screens v2.dc.html` (screens 1a through 1d) in the
`design_handoff_signal_lab_screens` bundle. Every value in `tokens-v2.css` is one that appears
literally in that markup. The bundle's `README.md` was read but not trusted, and the bundle's own
`tokens.css` is byte-identical to the v1 `design/ds/tokens.css`, so it carries nothing new.

`tokens-v2.css` replaces `tokens.css`; it does not layer on top of it. Shared names carry different
values in each file, so a build loads one or the other. Nothing in `design/ds/` was modified.

## What changed from v1

**Borders gave way to shadow tiers.** v1 outlined panels with a hairline and gave elevation a single
`--shadow-card` plus a heavier `--shadow-float`. v2 removes the outline entirely: the markup carries
28 explicit `border: none` declarations, and a panel now separates from the page by fill and shadow
and from a sibling panel by whitespace. Elevation became three named tiers, each an inset top
highlight over two to three ambient layers, plus a separate inset shadow for fields. Every remaining
1px border in the file sits on a true divider (nav right edge, header bottom, in-card row separator,
sidebar left edge) or on a control (input, badge, quiet button).

**The gray hierarchy collapsed from three levels to two.** v1 defined `--ink`, `--ink-2`, and
`--ink-3` (`#5f6c85`) as a working three-step ramp. In v2, `#e6ebf5` and `#9aa7bf` carry 70 and 162
uses respectively and do all the work. `#5f6c85` never appears as a text color at all; it survives
only as the fill of an ancestor lineage dot. A third ink does exist, `#8b9ab6`, but it appears three
times and only on field labels, so it is a narrow exception rather than a tier.

**Body copy is now near-white.** The v1 pattern put body text in mid-gray and reserved near-white for
headings. v2 inverts it: body copy is `#e6ebf5` at 15px/400 with metadata in `#9aa7bf`. Section
headings went the other way and are deliberately quiet, 14px at weight 400 in `#9aa7bf`, so the
content under a heading is louder than the heading. Build against this inversion, because the
washed-out result of the old arrangement is exactly what the revision was correcting.

**`ch` line caps became pixel caps.** `ch` measures the zero glyph, which is wider than the average
letter in this stack, so the old caps ran long. v2 uses 560px for body measure, 470px for secondary
paragraphs, and 500px for the blurred-layer card body. Three `ch` values survive in the markup and
should be converted on the way into code: `40ch` and `46ch` on the sign-in card, `26ch` in the agent
sidebar, becoming roughly 340px, 390px, and 215px.

**Font.** The UI stack is now `-apple-system, BlinkMacSystemFont, 'SF Pro Text', Manrope, 'Segoe UI',
'Helvetica Neue', sans-serif`. Manrope replaces Satoshi as of this revision; the production follow-up
is self-hosting Manrope at 400/500/600/700. Do not reorder the stack.

## Where the handoff README contradicts its own markup

These are factual errors, not taste calls. Each was checked against the markup line by line.

**Tier 2 is stated correctly but attributed wrongly.** The README's tier-2 block
(`0 8px 20px rgba(3,6,12,0.36), 0 24px 52px rgba(3,6,12,0.28)`) does appear in the file, twice, on
the proposal sidebar and the create-room card. But the README names the sign-in aside as a third
tier-2 consumer, and that element instead carries `0 10px 26px rgba(3,6,12,0.34), 0 28px 60px
rgba(3,6,12,0.26)` - softer at both blur stops. One of the three named consumers does not use the
stated value.

**Tier 3 is stated correctly but only one element uses it.** The README's tier-3 block
(`0 20px 48px rgba(2,4,9,0.55), 0 44px 96px rgba(2,4,9,0.42)`) appears exactly once, on the fork
modal. The README names the sign-in card as the other tier-3 consumer, and that card is still
carrying v1's `--shadow-float` verbatim: `0 14px 34px rgba(2,4,9,0.5), 0 32px 72px rgba(2,4,9,0.36)`.
The sign-in card was never migrated to the new tier.

**The emblem recipe has five literal forms, not one.** The README gives a single recipe: background
`rgba(C, 0.22)`, inset ring `rgba(C, 0.45)`, outer glow `0 0 16px rgba(C, 0.24)`. That is true only
for the green, cyan, and violet status emblems. The amber room-identity emblem uses 0.2 / 0.42 /
`0 0 14px` at 0.2. The neutral repo-row emblem uses 0.16 / 0.34 / `0 0 14px` at 0.12. The 25px
provenance emblem uses 0.18 / 0.34 / `0 0 12px` at 0.14. The 24px disclosure-header emblems use 0.18
/ 0.34 with no outer glow at all. The README partially acknowledges the last two by size but still
asserts a fixed `0.22` background, which is wrong in four of the five cases.

**The chevron rule is violated by the components the README names.** The README states that every
disclosure header carries a chevron, rotated `-90deg` when collapsed and `0deg` when open, and its
own toggle inventory lists "The change" and "Credit chain" as chevron-bearing disclosure headers.
Neither header contains a chevron element in the markup. Those two are also the only headers matching
the README's stated 24px-emblem disclosure pattern, so the pattern is violated in both of its
instances. The chevrons that do exist behave correctly: five are rotated `-90deg` on collapsed diff
rows and a collapsed Q&A row, and the un-rotated ones sit on the expanded "Provenance verified" and
"Options" disclosures. The "Diff" panel header also has no chevron, though the README does not list
it as a toggle.

**The inverted pill spec is incomplete for the auth button.** The README's inverted-pill block
specifies 13.5px/600 with `0 8px 22px rgba(11,14,20,0.55)`, and explicitly overrides only the padding
for the sign-in auth button. That button in fact also differs in size and shadow: 14px and
`0 8px 24px rgba(11,14,20,0.6)`. The two other inverted pills match the stated block exactly.

**Two line-heights are missing from the type table.** `1.6` is used twice and mentioned only in prose
elsewhere in the README; `1.3` is used twice, on the two-line profile-row label, and appears nowhere
in the README at all.

Where the README is accurate and worth keeping: the tier-1 shadow is unanimous across all five of its
uses, the radii table matches every literal radius in the file, the residual `ch` values are disclosed
honestly with correct conversions, and the 216px rail, 316px agent column, and 54px header are all
confirmed.
