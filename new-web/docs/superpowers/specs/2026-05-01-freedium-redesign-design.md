# Freedium Home Page Redesign

_2026-05-01_

## Overview

Re-skin the Freedium home page to match the editorial dark-theme prototype in `freedium_handoff/freedium/project/Freedium Redesign.html`. The header structure is preserved as-is (all existing functionality retained); every other section of the home page gets a visual overhaul. Both dark and light modes are supported — dark matches the prototype exactly, light uses a complementary warm parchment palette.

## Constraints

- SvelteKit + Tailwind CSS v4 + bits-ui / shadcn components
- Header structure unchanged: ThemeToggle, PayButtons, ExtensionsButton, ReportProblem all stay in place
- No new server-side data fetching; feed cards use existing static placeholder data
- No changes to the article page (`[slug]` route)

---

## 1. Color system + typography (`app.css`)

Replace the current HSL custom-property set with an oklch token set.

**Dark mode tokens (match prototype):**
```
--bg:          oklch(0.18 0.008 95)   /* warm off-black body */
--bg-2:        oklch(0.215 0.009 95)  /* card surface */
--bg-3:        oklch(0.255 0.010 95)  /* elevated surface */
--line:        oklch(0.30 0.008 95)   /* subtle border */
--line-2:      oklch(0.36 0.010 95)   /* visible border */
--ink:         oklch(0.96 0.005 95)   /* primary text */
--ink-2:       oklch(0.78 0.008 95)   /* secondary text */
--ink-3:       oklch(0.58 0.010 95)   /* tertiary text */
--ink-4:       oklch(0.45 0.010 95)   /* muted text */
--accent:      oklch(0.82 0.10 145)   /* sage green */
--accent-deep: oklch(0.55 0.08 145)   /* deep green (focus rings) */
```

**Light mode tokens (warm parchment complement):**
```
--bg:          oklch(0.97 0.008 95)   /* warm parchment */
--bg-2:        oklch(0.93 0.008 95)   /* card surface */
--bg-3:        oklch(0.89 0.009 95)   /* elevated surface */
--line:        oklch(0.82 0.008 95)
--line-2:      oklch(0.74 0.010 95)
--ink:         oklch(0.18 0.008 95)   /* dark text */
--ink-2:       oklch(0.35 0.008 95)
--ink-3:       oklch(0.52 0.010 95)
--ink-4:       oklch(0.65 0.010 95)
--accent:      oklch(0.55 0.10 145)   /* deeper green for light bg */
--accent-deep: oklch(0.40 0.08 145)
```

**Typography:** Add Google Fonts import for Instrument Serif (ital 0;1) + JetBrains Mono (wght 400;500) + Inter (wght 400;500;600). Wire up `--font-serif`, `--font-mono`, `--font-sans` CSS variables.

Map existing Tailwind semantic tokens (`--primary`, `--background`, etc.) to these new primitives so existing components that use them continue to work.

---

## 2. Header re-skin (`Header.svelte`)

Structure unchanged. Visual changes only:

- Brand "Freedium" text: switch to `font-serif` italic, with a sage-green `·` dot prefix (`·&nbsp;Freedium`)
- The `beta` chip: mono font, uppercase, small border, `--ink-3` color — matches design's `.brand-tag`
- Nav/action buttons: adopt new `--bg-2` hover backgrounds, `--line` borders, `--ink-2`/`--ink` color states
- "Add Article" CTA button: `--accent` background, dark text, matches design's `.submit-btn`
- Sticky backdrop: `--bg` with `backdrop-filter: blur(8px)`
- ThemeToggle, PayButtons, ExtensionsButton, ReportProblem: re-skinned with new tokens but position unchanged

---

## 3. Hero — `HomeBanner.svelte` + `UrlBox.svelte`

Replace the current minimal banner layout with the full design hero.

**HomeBanner.svelte:**
- Mono eyebrow: pulsing green dot + "Open access reader · est. 2023"
- `h1` (serif, `clamp(40px, 6vw, 76px)`): `Reading,` then italic accent `without the wall.`
- Italic serif lede (22px): "Paste any paywalled article link below…"
- Renders `<UrlBox />` as the unlock bar
- Below UrlBox: unlock-meta row with three items — articles-unlocked stat, keyboard hints (`↵` / `⇧↵`), avg-fetch stat

**UrlBox.svelte:**
- Three-column grid: `[pre-column] [input] [button]`
- Pre-column: dashed right border, link icon, mono `https://` label
- Input: full-width, transparent bg, 14.5px sans
- Button: `--accent` background, "Unlock →" label, rounded-lg
- Focus-within: border switches to `--accent-deep`
- Keyboard: `Enter` submits (already works via form)

---

## 4. Feed section header (new markup in `+page.svelte`)

Add above the masonry grid:

```
[left]                              [right]
— Recently unlocked by community    [Latest][Trending][This week][Long reads][Following]
What people are reading (italic h2)
```

- Section-head is a flex row, bottom-bordered, `max-width: 1240px`
- Filter bar: pill-group, `--bg-2` background, active pill gets `--bg-3`
- Filter state is local UI only (no data filtering wired up)

---

## 5. Type changes (`src/lib/types/blog.ts`)

Add an optional `cardType` discriminator to `BlogPost`:

```ts
export type CardType = 'standard' | 'featured' | 'quote' | 'stat';

// Add to BlogPost:
cardType?: CardType;
quoteText?: string;   // used when cardType === 'quote'
statValue?: string;   // used when cardType === 'stat' (e.g. "94%")
statLabel?: string;
statDesc?: string;
```

`cardType` defaults to `'standard'` when absent. The two synthetic cards added in `+page.svelte` use `cardType: 'quote'` and `cardType: 'stat'` respectively and can omit irrelevant fields (title, excerpt, slug become empty strings or are ignored by the card renderer).

---

## 6. `BlogCard.svelte`

Replace current card with design-spec card:

**Image area (`.thumb`):**
- Striped placeholder div (CSS repeating-linear-gradient) with a mono tag label
- Aspect ratios: `16/10` default, `4/5` for `tall`, `21/10` for `wide`/`featured`
- Palette variants: `ph-warm`, `ph-cool`, `ph-green`, `ph-rose`, `ph-violet`, `ph-sand` — assigned by `id % 6`
- `featured` cards get a "Featured" badge pill; all non-quote/non-stat cards get a read-time badge
- Still links to `/{slug}` as before (quote/stat cards are non-linking)

**Standard/featured body:**
- Topic pip (rotated square in accent color) + collection name (mono, uppercase, accent)
- Serif title (`24px`; `featured` gets `32px`)
- Excerpt (`ink-2`, 13.5px)
- Meta row: author avatar (22×22, gradient, mono initials) + name + dot-sep + date + save button (right-aligned bookmark icon)

**Quote card (cardType === 'quote'):**
- No image. Renders: large serif `"` mark in accent, italic serif blockquote (`quoteText`), mono `cite`
- Non-linking

**Stat card (cardType === 'stat'):**
- No image. Renders: large italic serif number (`statValue`), mono label (`statLabel`), small desc (`statDesc`)
- Non-linking

**Avatar palettes** (6 gradient variants, cycle by `id % 6`):
```
0: oklch warm orange  1: teal   2: green
3: gold               4: rose   5: indigo
```

---

## 7. `Footer.svelte`

Replace current footer layout:

- Left: mono "By Freedium & **N** contributors." + italic serif "— made with care."
- Center: nav links — About · Privacy · Terms · RSS · GitHub · Codeberg
- Right: GitHub + Codeberg icon buttons (existing, keep)
- Layout: flex row, space-between, wraps on mobile
- Tokens: `--line` top border, `--ink-3` text, `--bg` background

---

## Files to change

| File | Change |
|------|--------|
| `src/app.css` | Replace color token set, add font imports + variables |
| `src/lib/types/blog.ts` | Add `cardType`, `quoteText`, `statValue`, `statLabel`, `statDesc` optional fields |
| `src/lib/elements/Header.svelte` | Visual re-skin only |
| `src/lib/elements/HomeBanner.svelte` | Full rewrite to design hero |
| `src/lib/elements/UrlBox.svelte` | Full rewrite to unlock bar |
| `src/routes/+page.svelte` | Add section header; add synthetic quote + stat cards to items array |
| `src/lib/elements/BlogCard.svelte` | Full rewrite to design card |
| `src/lib/elements/Footer.svelte` | Full rewrite to design footer |

No new files needed. No changes to `[slug]` route or any other component.
