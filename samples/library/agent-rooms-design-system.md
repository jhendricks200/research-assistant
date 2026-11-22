---
title: 'Agent Rooms: Signal Lab component library'
source_type: reference
status: published
topics: [Agent Rooms, Design]
tags: [design system, components]
entities: [Signal Lab]
---
# Signal Lab - component library

Extracted from **`design/direction-c2.html`** ("Agent Rooms · Signal Lab · Night Market"), the blessed direction. Every literal color, shadow, spacing, radius, and font value in this folder is copied verbatim from that file. If direction-c2.html changes, these previews and `tokens.css` need to be re-synced by hand; nothing here is generated.

Do not treat `direction-a.html`, `direction-b.html`, or `direction-c.html` as sources - they were earlier explorations and are not blessed. `design/reference/` holds screenshot frames used during review; it is gitignored and not part of the shipped design system.

## Files

- `tokens.css` - machine-readable custom properties for every token, both themes via `[data-theme]` on `:root`. Drop this into a real build as-is.
- `tokens.html` (Foundations) - color swatches, type scale, spacing, radii, and shadow tiers, rendered in both themes. This v1 page names Satoshi (Fontshare / Indian Type Foundry) as the UI sans. The font files are no longer kept in the repository, because the Fontshare licence does not allow redistributing them, so the page falls back to system fonts unless Satoshi is installed locally. The v2 stack in `tokens-v2.css` supersedes it; the mono instrumentation stack is unchanged.
- `shell.html` (Layout) - the four-zone room shell (rail / header / feed / agent) at reduced scale.
- `left-rail.html` (Layout) - the left nav rail at native 236px width: brand mark, search, New room, room list, this-room section, settings, and the profile row with theme toggle.
- `proposal-card.html` (Components) - every card state: open/proposed, a forced hover state, fork-live, in review, adopted with full ceremony (banner, lineage thread, credit split, remix note), and a constructed rejected state (see Ambiguities).
- `chat.html` (Components) - the group chat timeline with plain messages interleaved with proposal cards, plus the private agent sidebar chat with its worked-for row.
- `composer.html` (Components) - the floating room composer (plus button, attach-proposal chip, mic, circular send) and the private agent composer, each at rest and in a forced focus state.
- `forms.html` (Components) - the Codex-style form surface tiers: inset input surface with luminous focus ring, floating panel surface, the modal box on its blurred scrim, and the composer-language button pills.
- `chips-badges.html` (Components) - state badges, the build status chip (including a constructed failing variant), live signal indicators (pulsing dot, blinking fork node, adopted node), member avatars with presence, and environment rail rows.

Every preview file's first line is a marker comment (`<!-- @dsCard group="..." -->`) used to group these pages in a design-system index. Every preview renders both themes side by side as fixed panels - none of it depends on the OS or browser color scheme; direction-c2.html's own theme toggle is a runtime nicety and is shown in `left-rail.html` purely as a static visual (moon in the dark panel, sun in the light panel), not a working switch.

## Ambiguities found (not fixed silently)

- **Rejected state.** direction-c2.html never shows a rejected proposal. `proposal-card.html` constructs one using the existing `--rose` token (which is defined in `:root` but applied nowhere in the source file) and a `.rejection-note` styled like the existing `.remix-note` pattern. This is an invented state, not an extracted one.
- **`--rose` token, generally.** Same root cause: `--rose` / light-mode `#c94b60` and dark-mode `#f77c8f` exist in the token block but are never consumed anywhere in direction-c2.html. Its intended use (error state? rejected? destructive action?) is not specified by the source. Used here for "rejected" and "build failing" as the most plausible reading.
- **Failing build-chip.** `.build-chip` in the source only ever renders the passing/green state. The failing variant in `chips-badges.html` is constructed by swapping the color to `--rose` and freezing the pulse animation; the source never confirms this is the intended failing treatment.
- **Type scale and spacing are not tokenized.** direction-c2.html never centralizes font sizes, spacing, or radii into custom properties (only color, shadow, and a single `--radius: 12px` are tokens). `tokens.css` and `tokens.html` document the literal values in use as a reference, not as enforceable variables, because the source doesn't have them as variables either.
- **Shell at reduced scale.** `shell.html` compresses the native 236px / 1fr / 372px column widths and 58px header row proportionally to fit a documentation-sized frame. The proportions are preserved; the pixel values are not native.
