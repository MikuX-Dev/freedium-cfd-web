# Freedium Home Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the Freedium home page to match the editorial dark-theme prototype from the design handoff, with a complementary warm parchment light mode.

**Architecture:** Replace the HSL-based Tailwind token system with an oklch custom-property system (`--bg`, `--ink`, `--accent`, etc.). New components use these tokens directly via CSS custom properties in scoped `<style>` blocks. Existing components (Header, SearchDialog, UI primitives) continue to work because Tailwind's semantic token names (`--color-background`, `--color-primary`, etc.) are remapped to the new primitives. Header structure is preserved; only visual appearance changes.

**Tech Stack:** SvelteKit 2 + Svelte 5 runes, Tailwind CSS v4 (`@tailwindcss/vite`), bits-ui, Google Fonts (Instrument Serif, JetBrains Mono, Inter), `svelte-bricks` for masonry.

**Spec:** `docs/superpowers/specs/2026-05-01-freedium-redesign-design.md`

---

## File Map

| File | Change |
|------|--------|
| `src/app.html` | Add Google Fonts `<link>` tags |
| `src/app.css` | Replace HSL tokens with oklch system; add font vars |
| `src/lib/types/blog.ts` | Add `CardType`, `cardType`, `quoteText`, `statValue`, `statLabel`, `statDesc` |
| `src/lib/elements/Header.svelte` | Visual re-skin only (structure unchanged) |
| `src/lib/elements/HomeBanner.svelte` | Full rewrite to design hero |
| `src/lib/elements/UrlBox.svelte` | Full rewrite to unlock bar |
| `src/routes/+page.svelte` | Section header + synthetic quote/stat cards |
| `src/lib/elements/BlogCard.svelte` | Full rewrite to design card |
| `src/lib/elements/Footer.svelte` | Full rewrite to design footer |

---

## Task 1: Google Fonts + CSS token system

**Files:**
- Modify: `src/app.html`
- Modify: `src/app.css`

### Step 1.1 — Add Google Fonts to app.html

- [ ] Open `src/app.html` and add three `<link>` tags inside `<head>`, immediately before `%sveltekit.head%`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

Full resulting `<head>` section (keep all existing scripts):

```html
<head>
  <meta charset="utf-8" />
  <link rel="icon" href="%sveltekit.assets%/favicon.png" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />

  <!-- FOUC prevention -->
  <script>
    localStorage.theme === 'dark' ||
    (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? document.documentElement.classList.add('dark')
      : document.documentElement.classList.remove('dark');
  </script>

  <!-- Iframe resize communication handlers -->
  <script>
    window._resizeIframe = function (obj) {
      const logMessage = `Received _resizeIframe call: iframe=${obj.iframe ? obj.iframe.id : 'unknown'}, height=${obj.height}`;
      if (obj.iframe) { obj.iframe.height = obj.height; }
      console.log(obj.iframe);
      console.log(logMessage);
    };
    window.addEventListener('message', function (event) {
      console.log('Event data:', JSON.stringify(event.data));
      if (typeof event.data === 'string') {
        try {
          let parsedData = JSON.parse(event.data);
          console.log('Event data type:', typeof parsedData);
          if (parsedData && parsedData.method === 'iframe.resize' && parsedData.context === 'iframe.resize') {
            console.log('Resizing iframe - Source:', parsedData.src, 'Height:', parsedData.height, 'Method:', parsedData.method);
            const iframes = document.querySelectorAll('iframe');
            for (let iframe of iframes) {
              if (iframe.src === parsedData.src) {
                console.log('Setting iframe height to:', parsedData.height);
                console.log(iframe);
                iframe.height = parsedData.height;
                break;
              }
            }
          }
        } catch (e) {
          console.debug('Non-JSON message received:', e);
        }
      }
    });
  </script>

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

  %sveltekit.head%
</head>
```

### Step 1.2 — Replace CSS token system in app.css

- [ ] Replace the entire content of `src/app.css` with the following. Key changes: `@theme` now maps Tailwind semantic tokens to `var(--*)` primitives; `@layer base` defines oklch values for light (`:root`) and dark (`.dark`); font families added to `@theme`. All existing Shiki/medium-zoom/transition styles are preserved.

```css
@import 'tailwindcss';

@custom-variant dark (&:where(.dark, .dark *));

@theme {
  /* Font families */
  --font-serif: "Instrument Serif", Georgia, serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
  --font-sans: "Inter", system-ui, sans-serif;

  /* Tailwind semantic tokens → oklch primitives */
  --color-border:                  var(--line);
  --color-input:                   var(--bg-2);
  --color-ring:                    var(--accent-deep);
  --color-background:              var(--bg);
  --color-foreground:              var(--ink);
  --color-primary:                 var(--accent);
  --color-primary-foreground:      oklch(0.18 0.02 145);
  --color-secondary:               var(--bg-2);
  --color-secondary-foreground:    var(--ink-2);
  --color-destructive:             oklch(0.55 0.20 25);
  --color-destructive-foreground:  oklch(0.97 0.005 95);
  --color-muted:                   var(--bg-2);
  --color-muted-foreground:        var(--ink-3);
  --color-accent:                  var(--bg-3);
  --color-accent-foreground:       var(--ink);
  --color-popover:                 var(--bg-2);
  --color-popover-foreground:      var(--ink);
  --color-card:                    var(--bg-2);
  --color-card-foreground:         var(--ink);

  --radius-lg: var(--radius);
  --radius-md: calc(var(--radius) - 2px);
  --radius-sm: calc(var(--radius) - 4px);
}

@layer base {
  :root {
    /* Light mode: warm parchment */
    --bg:          oklch(0.97 0.008 95);
    --bg-2:        oklch(0.93 0.008 95);
    --bg-3:        oklch(0.89 0.009 95);
    --line:        oklch(0.82 0.008 95);
    --line-2:      oklch(0.74 0.010 95);
    --ink:         oklch(0.18 0.008 95);
    --ink-2:       oklch(0.35 0.008 95);
    --ink-3:       oklch(0.52 0.010 95);
    --ink-4:       oklch(0.65 0.010 95);
    --accent:      oklch(0.55 0.10 145);
    --accent-deep: oklch(0.40 0.08 145);
    --radius: 0.5rem;
  }

  .dark {
    /* Dark mode: warm off-black editorial */
    --bg:          oklch(0.18 0.008 95);
    --bg-2:        oklch(0.215 0.009 95);
    --bg-3:        oklch(0.255 0.010 95);
    --line:        oklch(0.30 0.008 95);
    --line-2:      oklch(0.36 0.010 95);
    --ink:         oklch(0.96 0.005 95);
    --ink-2:       oklch(0.78 0.008 95);
    --ink-3:       oklch(0.58 0.010 95);
    --ink-4:       oklch(0.45 0.010 95);
    --accent:      oklch(0.82 0.10 145);
    --accent-deep: oklch(0.55 0.08 145);
  }

  body, html { scroll-behavior: smooth; }

  /* Smooth theme transitions */
  * {
    transition: background-color 500ms ease, border-color 500ms ease,
                box-shadow 500ms ease, color 500ms ease;
  }
  html, body, [class*="bg-"], [class*="text-"], [class*="border-"] {
    transition: background-color 500ms ease, border-color 500ms ease,
                box-shadow 500ms ease, color 500ms ease;
  }
  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; }
  }
}

@layer base {
  * { @apply border-border; }
  body { @apply bg-background text-foreground font-sans; }
  ::selection { @apply bg-primary text-primary-foreground; }
}

.medium-zoom-overlay,
.medium-zoom-image--opened {
  z-index: 999;
}

.medium-zoom-overlay {
  background: var(--bg) !important;
}

@layer base {
  /* Shiki syntax highlighting */
  pre.shiki { counter-reset: line-number; }
  pre.shiki code { display: grid; }
  pre.shiki,
  pre.shiki span { background-color: transparent; }

  pre.shiki .line { counter-increment: line-number; }
  pre.shiki .line::before {
    content: counter(line-number);
    color: var(--ink-4);
    display: inline-block;
    text-align: right;
    margin-right: 1em;
    width: 2ch;
  }

  pre.shiki .diff.add  { background-color: oklch(0.72 0.18 145 / 0.25); }
  pre.shiki .diff.remove { background-color: oklch(0.55 0.20 25 / 0.35); }
  html.dark pre.shiki .diff.add    { background-color: oklch(0.45 0.12 145 / 0.35); }
  html.dark pre.shiki .diff.remove { background-color: oklch(0.35 0.15 25 / 0.45); }

  pre.shiki code { @apply select-text cursor-text focus:outline-none; }
}
```

### Step 1.3 — Verify type-check passes

- [ ] Run: `bun run check`
- Expected: no errors (zero TypeScript/Svelte issues)

### Step 1.4 — Start dev server and verify visually

- [ ] Run: `bun run dev`
- Open `http://localhost:5173` in a browser
- Expected: page background is warm parchment (light mode) or warm off-black (dark mode), fonts load (Instrument Serif visible in any serif elements), sage-green primary buttons

### Step 1.5 — Commit

```bash
git add src/app.html src/app.css
git commit -m "feat: replace CSS token system with oklch design palette"
```

---

## Task 2: Blog type extensions

**Files:**
- Modify: `src/lib/types/blog.ts`

### Step 2.1 — Add CardType and optional fields to BlogPost

- [ ] Replace the full content of `src/lib/types/blog.ts`:

```typescript
export type BlogPostSize = 'small' | 'medium' | 'large' | 'wide' | 'tall';

export type CardType = 'standard' | 'featured' | 'quote' | 'stat';

export interface BlogCollection {
  name: string;
  avatarId: string;
}

export interface BlogPost {
  id: number;
  title: string;
  excerpt: string;
  imageUrl?: string;
  bottomImageUrl?: string | null;
  size?: BlogPostSize | null;
  readingTime: string;
  publishedAt: string;
  collection?: BlogCollection | null;
  creator: string;
  slug: string;
  cardType?: CardType;
  quoteText?: string;
  statValue?: string;
  statLabel?: string;
  statDesc?: string;
}

export interface SearchPost {
  id: string;
  title: string;
  date: Date;
  excerpt: string;
  imageUrl: string;
}
```

### Step 2.2 — Verify types compile

- [ ] Run: `bun run check`
- Expected: PASS — no new errors (existing BlogCard.svelte still receives the same props it had before since all new fields are optional)

### Step 2.3 — Commit

```bash
git add src/lib/types/blog.ts
git commit -m "feat: add CardType discriminator and card-specific fields to BlogPost"
```

---

## Task 3: Header visual re-skin

**Files:**
- Modify: `src/lib/elements/Header.svelte`

**What changes:** brand mark styling (serif italic + green dot), beta chip (mono border style), header background/border classes switched from hardcoded zinc to semantic token classes. All logic, event handlers, and sub-components remain identical.

### Step 3.1 — Update Header.svelte

- [ ] Replace the full content of `src/lib/elements/Header.svelte`:

```svelte
<script lang="ts">
  import ProgressLine from './ProgressLine.svelte';
  import ThemeToggle from './ThemeToggle.svelte';
  import ReportProblem from './ReportProblem.svelte';
  import PayButtons from './PayButtons.svelte';
  import ExtensionsButton from './ExtensionsButton.svelte';
  import SearchDialog from './SearchDialog.svelte';
  import Menu from '@lucide/svelte/icons/menu';
  import X from '@lucide/svelte/icons/x';
  import Search from '@lucide/svelte/icons/search';
  import Plus from '@lucide/svelte/icons/plus';
  import TeenyiconsCupSolid from '~icons/teenyicons/cup-solid';
  import SimpleIconsLiberapay from '~icons/simple-icons/liberapay';
  import SimpleIconsDiscord from '~icons/simple-icons/discord';

  import { Button } from '$lib/components/ui/button/index.js';
  import { onMount } from 'svelte';

  let isNavOpen = $state(false);
  let isSearchOpen = $state(false);
  let isHeaderVisible = $state(true);
  let lastScrollY = $state(0);

  function handleScroll() {
    const currentScrollY = window.scrollY;
    const documentHeight = document.documentElement.scrollHeight - window.innerHeight;
    const scrollPercentage = (currentScrollY / documentHeight) * 100;
    if (scrollPercentage > 5) {
      isHeaderVisible = lastScrollY > currentScrollY;
    } else {
      isHeaderVisible = true;
    }
    lastScrollY = currentScrollY;
  }

  onMount(() => {
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  });

  const toggleNav = () => { isNavOpen = !isNavOpen; };
  const toggleSearch = () => { isSearchOpen = !isSearchOpen; };
</script>

<nav
  id="header"
  class="header-nav"
  style="transform: translateY({isHeaderVisible ? '0' : '-100%'})"
>
  <ProgressLine />

  <div class="container flex items-center justify-between h-14 px-4 mx-auto">
    <!-- Logo -->
    <a class="brand-link" href="/">
      <span class="brand-mark"><span class="brand-dot">·</span> Freedium</span>
      <span class="brand-tag">beta</span>
    </a>

    <!-- Desktop Navigation -->
    <div class="items-center hidden gap-1 md:flex">
      <Button variant="ghost" size="icon" onclick={toggleSearch} title="Search">
        <Search class="size-5" />
      </Button>

      <ExtensionsButton />

      <div class="w-px h-5 mx-1" style="background: var(--line)"></div>

      <div class="flex items-center gap-0.5">
        <PayButtons name="Ko-fi" url="https://ko-fi.com/zhymabekroman" icon={TeenyiconsCupSolid} showLabel={false} />
        <PayButtons name="Liberapay" url="https://liberapay.com/ZhymabekRoman/" icon={SimpleIconsLiberapay} showLabel={false} />
        <PayButtons name="Discord" url="https://discord.gg/dAxCuG9nYM" icon={SimpleIconsDiscord} showLabel={false} />
      </div>

      <div class="w-px h-5 mx-1" style="background: var(--line)"></div>

      <ThemeToggle />
      <ReportProblem compact={true} />

      <Button size="sm" class="ml-2 gap-1.5">
        <Plus class="size-4" />
        <span>Submit link</span>
      </Button>
    </div>

    <!-- Mobile Navigation -->
    <div class="flex items-center gap-1 md:hidden">
      <Button variant="ghost" size="icon" onclick={toggleSearch} title="Search">
        <Search class="size-5" />
      </Button>
      <ThemeToggle />
      <ReportProblem compact={true} />
      <Button
        variant="ghost"
        size="icon"
        onclick={toggleNav}
        aria-expanded={isNavOpen}
        aria-controls="mobile-menu"
      >
        {#if isNavOpen}
          <X class="size-5" />
        {:else}
          <Menu class="size-5" />
        {/if}
        <span class="sr-only">Toggle menu</span>
      </Button>
    </div>
  </div>

  <!-- Mobile Menu -->
  {#if isNavOpen}
    <div id="mobile-menu" class="mobile-menu md:hidden">
      <div class="flex flex-col gap-2 p-4">
        <Button class="w-full gap-2">
          <Plus class="size-4" />
          <span>Submit link</span>
        </Button>

        <div class="mobile-section">
          <p class="mobile-section-label">Support Freedium</p>
          <div class="flex flex-wrap gap-2">
            <PayButtons name="Ko-fi" url="https://ko-fi.com/zhymabekroman" icon={TeenyiconsCupSolid} showLabel={true} />
            <PayButtons name="Liberapay" url="https://liberapay.com/ZhymabekRoman/" icon={SimpleIconsLiberapay} showLabel={true} />
            <PayButtons name="Discord" url="https://discord.gg/dAxCuG9nYM" icon={SimpleIconsDiscord} showLabel={true} />
          </div>
        </div>

        <div class="mobile-section">
          <p class="mobile-section-label">Browser Extensions</p>
          <ExtensionsButton />
        </div>
      </div>
    </div>
  {/if}
</nav>

<SearchDialog bind:open={isSearchOpen} />

<style>
  .header-nav {
    position: sticky;
    top: 0;
    z-index: 50;
    width: 100%;
    transition: transform 300ms ease;
    border-bottom: 1px solid var(--line);
    background: color-mix(in oklch, var(--bg) 90%, transparent);
    backdrop-filter: blur(8px);
  }

  .brand-link {
    display: flex;
    align-items: baseline;
    gap: 10px;
    text-decoration: none;
  }
  .brand-mark {
    font-family: var(--font-serif);
    font-size: 22px;
    font-style: italic;
    letter-spacing: -0.01em;
    color: var(--ink);
    white-space: nowrap;
  }
  .brand-dot { color: var(--accent); }

  .brand-tag {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-3);
    border: 1px solid var(--line-2);
    padding: 2px 6px;
    border-radius: 3px;
    background: var(--bg-2);
  }

  .mobile-menu {
    width: 100%;
    background: var(--bg);
    border-top: 1px solid var(--line);
  }
  .mobile-section {
    padding-top: 8px;
    margin-top: 8px;
    border-top: 1px solid var(--line);
  }
  .mobile-section-label {
    margin-bottom: 8px;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
</style>
```

### Step 3.2 — Verify type-check

- [ ] Run: `bun run check`
- Expected: PASS

### Step 3.3 — Verify visually

- [ ] With `bun run dev` running, check `http://localhost:5173`:
  - Header background is warm (not pure white/black)
  - "· Freedium" brand mark is serif italic with green dot
  - "beta" chip has border and mono style
  - All existing buttons (search, extensions, pay, theme toggle) still appear

### Step 3.4 — Commit

```bash
git add src/lib/elements/Header.svelte
git commit -m "feat: re-skin header with editorial typography and oklch tokens"
```

---

## Task 4: Hero section (HomeBanner + UrlBox)

**Files:**
- Modify: `src/lib/elements/HomeBanner.svelte`
- Modify: `src/lib/elements/UrlBox.svelte`

### Step 4.1 — Rewrite HomeBanner.svelte

- [ ] Replace the full content of `src/lib/elements/HomeBanner.svelte`:

```svelte
<script lang="ts">
  import UrlBox from './UrlBox.svelte';
</script>

<section class="hero">
  <div class="eyebrow">
    <span class="pulse"></span>
    Open access reader · est. 2023
  </div>
  <h1>Reading, <em>without the wall.</em></h1>
  <p class="lede">Paste any paywalled article link below — Freedium fetches an open, ad-free version you can keep.</p>
  <UrlBox />
  <div class="unlock-meta">
    <div class="stat">↳ <strong>1.2M</strong> articles unlocked this month</div>
    <div class="stat">
      <kbd>↵</kbd> to unlock · <kbd>⇧↵</kbd> to save without opening
    </div>
    <div class="stat"><strong>26ms</strong> avg fetch</div>
  </div>
</section>

<style>
  .hero {
    max-width: 980px;
    margin: 0 auto;
    padding: 72px 28px 36px;
    text-align: center;
  }

  .eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin-bottom: 24px;
  }
  .pulse {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 4px color-mix(in oklch, var(--accent) 20%, transparent);
  }

  h1 {
    font-family: var(--font-serif);
    font-weight: 400;
    font-size: clamp(40px, 6vw, 76px);
    line-height: 1.02;
    letter-spacing: -0.02em;
    margin: 0 0 18px;
    color: var(--ink);
  }
  h1 em {
    font-style: italic;
    color: var(--accent);
  }

  .lede {
    font-family: var(--font-serif);
    font-size: 22px;
    line-height: 1.4;
    color: var(--ink-2);
    max-width: 620px;
    margin: 0 auto 36px;
    font-style: italic;
  }

  .unlock-meta {
    max-width: 760px;
    margin: 14px auto 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-4);
    letter-spacing: 0.02em;
  }
  .stat {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .stat strong { color: var(--ink-2); font-weight: 500; }

  kbd {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--ink-3);
    border: 1px solid var(--line-2);
    padding: 2px 5px;
    border-radius: 3px;
    background: var(--bg-2);
  }

  @media (max-width: 640px) {
    .unlock-meta {
      flex-direction: column;
      gap: 8px;
      align-items: flex-start;
    }
  }
</style>
```

### Step 4.2 — Rewrite UrlBox.svelte

- [ ] Replace the full content of `src/lib/elements/UrlBox.svelte`:

```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  let url = $state('');

  async function handleSubmit(event: Event) {
    event.preventDefault();
    if (url.trim()) await goto(`/${url.trim()}`);
  }
</script>

<form class="unlock" onsubmit={handleSubmit}>
  <div class="pre">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    </svg>
    https://
  </div>
  <!-- svelte-ignore a11y_autofocus -->
  <input
    type="text"
    placeholder="paste an article link, or drop a Substack / Medium / NYT URL…"
    bind:value={url}
    autofocus
    aria-label="Article URL"
  />
  <button type="submit">
    Unlock
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
         stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M5 12h14M13 5l7 7-7 7"/>
    </svg>
  </button>
</form>

<style>
  .unlock {
    max-width: 760px;
    margin: 0 auto;
    background: var(--bg-2);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 6px;
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: stretch;
    gap: 0;
    transition: border-color 0.15s;
  }
  .unlock:focus-within { border-color: var(--accent-deep); }

  .pre {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 14px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-3);
    border-right: 1px dashed var(--line);
  }
  .pre svg { width: 14px; height: 14px; color: var(--accent); }

  input {
    background: transparent;
    border: none;
    outline: none;
    color: var(--ink);
    font-family: var(--font-sans);
    font-size: 14.5px;
    padding: 14px 16px;
    width: 100%;
  }
  input::placeholder { color: var(--ink-4); }

  button {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: var(--accent);
    color: oklch(0.18 0.02 145);
    border: none;
    border-radius: 8px;
    padding: 0 20px;
    font-weight: 600;
    font-size: 13px;
    font-family: var(--font-sans);
    cursor: pointer;
    transition: filter 0.15s;
    white-space: nowrap;
  }
  button:hover { filter: brightness(1.08); }
  button svg { width: 14px; height: 14px; }

  @media (max-width: 540px) {
    .unlock { grid-template-columns: 1fr auto; }
    .pre { display: none; }
  }
</style>
```

### Step 4.3 — Verify type-check

- [ ] Run: `bun run check`
- Expected: PASS

### Step 4.4 — Verify visually

- [ ] At `http://localhost:5173`:
  - Hero has large serif headline "Reading, *without the wall.*" with italic sage-green em
  - Unlock bar shows dashed `https://` prefix, full-width input, green "Unlock →" button
  - Stats row below unlock bar shows article count, keyboard hints, avg fetch time
  - Entering a URL and pressing Enter navigates to `/{url}` (existing behaviour preserved)

### Step 4.5 — Commit

```bash
git add src/lib/elements/HomeBanner.svelte src/lib/elements/UrlBox.svelte
git commit -m "feat: redesign hero section with editorial unlock bar"
```

---

## Task 5: BlogCard redesign

**Files:**
- Modify: `src/lib/elements/BlogCard.svelte`

### Step 5.1 — Rewrite BlogCard.svelte

- [ ] Replace the full content of `src/lib/elements/BlogCard.svelte`:

```svelte
<script lang="ts">
  import type { BlogPost } from '$lib/types';

  type Props = BlogPost;

  let {
    id,
    title,
    excerpt,
    size = 'medium',
    readingTime,
    publishedAt,
    collection = null,
    creator,
    slug,
    cardType = 'standard',
    quoteText = '',
    statValue = '',
    statLabel = '',
    statDesc = '',
  }: Props = $props();

  const isFeatured = cardType === 'featured';

  const palettes = ['ph-warm', 'ph-cool', 'ph-green', 'ph-rose', 'ph-violet', 'ph-sand'];
  const phClass = palettes[id % palettes.length];

  const phTags = [
    'editorial photo · 21:10', 'forest path', 'cliff coastline',
    'desk · still life', 'mushroom · macro', 'solar field · dusk', 'snow peaks'
  ];
  const phTag = phTags[id % phTags.length];

  const thumbClass = size === 'tall' ? 'thumb tall'
    : (size === 'wide' || isFeatured) ? 'thumb wide'
    : 'thumb';

  function initials(name: string): string {
    return name.split(' ').map((w) => w[0] ?? '').join('').slice(0, 2).toUpperCase();
  }

  const avClasses = ['av-1', 'av-2', 'av-3', 'av-4', 'av-5', 'av-6'];
  const avClass = avClasses[id % avClasses.length];

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch {
      return dateStr;
    }
  }
</script>

{#if cardType === 'quote'}
  <div class="card quote">
    <div class="qmark">"</div>
    <blockquote>{quoteText}</blockquote>
    <cite>— Editor's note · Vol. 04</cite>
  </div>
{:else if cardType === 'stat'}
  <div class="card stat-card">
    <div class="big">{statValue}</div>
    <div class="stat-lbl">— {statLabel}</div>
    <div class="stat-desc">{statDesc}</div>
  </div>
{:else}
  <a href={`/${slug}`} class="card-link">
    <article class="card" class:feat={isFeatured}>
      <div class={thumbClass}>
        <div class="thumb-ph {phClass}">
          <div class="ph-tag">{phTag}</div>
        </div>
        {#if isFeatured}
          <span class="badge"><span class="badge-dot"></span>Featured</span>
        {/if}
        <span class="read-time">{readingTime} min</span>
      </div>
      <div class="body">
        {#if collection}
          <div class="topic"><span class="pip"></span>{collection.name}</div>
        {/if}
        <h3 class="title">{title}</h3>
        {#if excerpt}
          <p class="excerpt">{excerpt}</p>
        {/if}
        <div class="meta">
          <div class="author">
            <span class="av {avClass}">{initials(creator)}</span>
            {creator}
          </div>
          <span class="dot-sep"></span>
          <span class="date">{formatDate(publishedAt)}</span>
          <button class="save" title="Save" onclick={(e) => e.preventDefault()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
            </svg>
          </button>
        </div>
      </div>
    </article>
  </a>
{/if}

<style>
  .card-link {
    display: block;
    text-decoration: none;
    color: inherit;
    margin-bottom: 24px;
  }

  .card {
    background: var(--bg-2);
    border: 1px solid var(--line);
    border-radius: 12px;
    overflow: hidden;
    transition: border-color 0.2s, transform 0.2s;
    position: relative;
  }
  /* quote and stat cards also need margin */
  .card.quote,
  .card.stat-card {
    margin-bottom: 24px;
  }
  .card-link:hover .card {
    border-color: var(--line-2);
    transform: translateY(-2px);
  }
  .card.feat { background: var(--bg-3); }

  /* ── Thumbnail ── */
  .thumb {
    position: relative;
    aspect-ratio: 16 / 10;
    overflow: hidden;
    background: var(--bg-3);
  }
  .thumb.tall  { aspect-ratio: 4 / 5; }
  .thumb.wide  { aspect-ratio: 21 / 10; }

  .thumb-ph {
    position: absolute; inset: 0;
    display: grid; place-items: center;
    background: repeating-linear-gradient(
      135deg,
      oklch(0.27 0.010 95) 0, oklch(0.27 0.010 95) 8px,
      oklch(0.24 0.009 95) 8px, oklch(0.24 0.009 95) 16px
    );
  }
  .ph-warm {
    background: repeating-linear-gradient(135deg,
      oklch(0.32 0.030 60) 0, oklch(0.32 0.030 60) 8px,
      oklch(0.27 0.025 60) 8px, oklch(0.27 0.025 60) 16px) !important;
  }
  .ph-cool {
    background: repeating-linear-gradient(135deg,
      oklch(0.30 0.025 220) 0, oklch(0.30 0.025 220) 8px,
      oklch(0.25 0.020 220) 8px, oklch(0.25 0.020 220) 16px) !important;
  }
  .ph-green {
    background: repeating-linear-gradient(135deg,
      oklch(0.32 0.030 145) 0, oklch(0.32 0.030 145) 8px,
      oklch(0.27 0.025 145) 8px, oklch(0.27 0.025 145) 16px) !important;
  }
  .ph-rose {
    background: repeating-linear-gradient(135deg,
      oklch(0.32 0.030 20) 0, oklch(0.32 0.030 20) 8px,
      oklch(0.27 0.025 20) 8px, oklch(0.27 0.025 20) 16px) !important;
  }
  .ph-violet {
    background: repeating-linear-gradient(135deg,
      oklch(0.32 0.030 290) 0, oklch(0.32 0.030 290) 8px,
      oklch(0.27 0.025 290) 8px, oklch(0.27 0.025 290) 16px) !important;
  }
  .ph-sand {
    background: repeating-linear-gradient(135deg,
      oklch(0.34 0.020 80) 0, oklch(0.34 0.020 80) 8px,
      oklch(0.29 0.018 80) 8px, oklch(0.29 0.018 80) 16px) !important;
  }

  .ph-tag {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--ink-4);
    background: var(--bg);
    padding: 6px 10px;
    border: 1px dashed var(--line-2);
    border-radius: 4px;
  }

  .badge {
    position: absolute;
    top: 12px; left: 12px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 9px;
    background: oklch(0.18 0.008 95 / 0.85);
    backdrop-filter: blur(6px);
    border: 1px solid oklch(0.96 0.005 95 / 0.10);
    border-radius: 999px;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--ink);
  }
  .badge-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: var(--accent);
  }
  .read-time {
    position: absolute;
    bottom: 12px; right: 12px;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.05em;
    color: oklch(0.96 0.005 95);
    background: oklch(0.18 0.008 95 / 0.85);
    backdrop-filter: blur(6px);
    padding: 3px 8px;
    border-radius: 4px;
  }

  /* ── Body ── */
  .body { padding: 18px 18px 16px; }

  .topic {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 10px;
  }
  .pip {
    display: inline-block;
    width: 4px; height: 4px;
    background: var(--accent);
    border-radius: 1px;
    transform: rotate(45deg);
  }

  .title {
    font-family: var(--font-serif);
    font-weight: 400;
    font-size: 24px;
    line-height: 1.15;
    letter-spacing: -0.01em;
    margin: 0 0 10px;
    color: var(--ink);
    text-wrap: balance;
  }
  .feat .title { font-size: 32px; }

  .excerpt {
    font-size: 13.5px;
    color: var(--ink-2);
    line-height: 1.55;
    margin: 0 0 16px;
  }

  /* ── Meta ── */
  .meta {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-top: 12px;
    border-top: 1px solid var(--line);
    font-size: 12px;
    color: var(--ink-3);
  }
  .author {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--ink-2);
  }
  .av {
    width: 22px; height: 22px;
    border-radius: 50%;
    display: grid; place-items: center;
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    color: white;
    flex-shrink: 0;
  }
  .av-1 { background: linear-gradient(135deg, oklch(0.65 0.13 35),  oklch(0.50 0.15 20)); }
  .av-2 { background: linear-gradient(135deg, oklch(0.65 0.10 200), oklch(0.45 0.12 220)); }
  .av-3 { background: linear-gradient(135deg, oklch(0.65 0.10 145), oklch(0.45 0.12 160)); }
  .av-4 { background: linear-gradient(135deg, oklch(0.70 0.10 80),  oklch(0.50 0.12 60)); }
  .av-5 { background: linear-gradient(135deg, oklch(0.65 0.13 320), oklch(0.45 0.14 290)); }
  .av-6 { background: linear-gradient(135deg, oklch(0.60 0.10 250), oklch(0.40 0.12 270)); }

  .dot-sep {
    width: 3px; height: 3px;
    background: var(--line-2);
    border-radius: 50%;
  }
  .date {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-4);
  }
  .save {
    margin-left: auto;
    background: transparent;
    border: 1px solid var(--line);
    color: var(--ink-3);
    width: 26px; height: 26px;
    border-radius: 6px;
    display: grid; place-items: center;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
  }
  .save:hover { color: var(--ink); border-color: var(--line-2); }
  .save svg { width: 12px; height: 12px; }

  /* ── Quote card ── */
  .card.quote {
    padding: 28px 22px;
    background: linear-gradient(180deg, var(--bg-3), var(--bg-2));
  }
  .qmark {
    font-family: var(--font-serif);
    font-size: 64px;
    line-height: 0.8;
    color: var(--accent);
    margin-bottom: 8px;
  }
  .card.quote blockquote {
    font-family: var(--font-serif);
    font-style: italic;
    font-size: 22px;
    line-height: 1.3;
    margin: 0 0 16px;
    color: var(--ink);
  }
  .card.quote cite {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    color: var(--ink-3);
    font-style: normal;
  }

  /* ── Stat card ── */
  .card.stat-card { padding: 22px; }
  .big {
    font-family: var(--font-serif);
    font-size: 76px;
    line-height: 1;
    letter-spacing: -0.03em;
    color: var(--accent);
    font-style: italic;
  }
  .stat-lbl {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin-top: 8px;
  }
  .stat-desc {
    font-size: 13px;
    color: var(--ink-2);
    margin-top: 12px;
    line-height: 1.5;
  }
</style>
```

### Step 5.2 — Verify type-check

- [ ] Run: `bun run check`
- Expected: PASS

### Step 5.3 — Verify visually

- [ ] At `http://localhost:5173`:
  - Cards show striped placeholder images with monospace tags
  - First card (id=0) will become featured once +page.svelte is updated in Task 6
  - Card bodies show collection name in accent color, serif titles, excerpt, author avatar, date

### Step 5.4 — Commit

```bash
git add src/lib/elements/BlogCard.svelte
git commit -m "feat: redesign BlogCard with editorial card variants"
```

---

## Task 6: Home page assembly

**Files:**
- Modify: `src/routes/+page.svelte`

### Step 6.1 — Rewrite +page.svelte

- [ ] Replace the full content of `src/routes/+page.svelte`:

```svelte
<script lang="ts">
  import Header from '$lib/elements/Header.svelte';
  import HomeBanner from '$lib/elements/HomeBanner.svelte';
  import BlogCard from '$lib/elements/BlogCard.svelte';
  import Footer from '$lib/elements/Footer.svelte';
  import Masonry from 'svelte-bricks';
  import type { BlogPost } from '$lib/types';

  let activeFilter = $state('Latest');
  const filters = ['Latest', 'Trending', 'This week', 'Long reads', 'Following'];

  const blogPosts: Omit<BlogPost, 'id'>[] = [
    {
      cardType: 'featured',
      title: 'Ten quiet habits of genuinely productive remote workers.',
      excerpt:
        'After interviewing 40 distributed engineers across six time zones, a pattern emerged — and it has nothing to do with calendars or coffee.',
      size: 'wide',
      readingTime: '12',
      publishedAt: '2023-04-10',
      collection: { name: 'Productivity', avatarId: '' },
      creator: 'Jane Doe',
      slug: '10-productivity-hacks-for-remote-workers',
    },
    {
      title: 'The future of AI in healthcare is already here — quietly.',
      excerpt:
        'Diagnostic models trained on 6M anonymized scans are now outperforming radiologists in narrow domains.',
      readingTime: '18',
      publishedAt: '2023-04-12',
      collection: { name: 'Tech in Medicine', avatarId: '' },
      creator: 'John Smith',
      slug: 'the-future-of-ai-in-healthcare',
    },
    {
      cardType: 'quote',
      quoteText:
        'Information wants to be free. Knowledge wants to be shared. Everything else is just plumbing.',
      title: '',
      excerpt: '',
      readingTime: '0',
      publishedAt: '2023-01-01',
      creator: 'Editor',
      slug: '',
    },
    {
      title: 'Cybersecurity essentials for small businesses.',
      excerpt:
        'Seven cheap, boring fixes that prevent 80% of breaches — and the one expensive one that handles the rest.',
      size: 'tall',
      readingTime: '8',
      publishedAt: '2023-04-16',
      collection: { name: 'Business Security', avatarId: '' },
      creator: 'Michael Brown',
      slug: 'cybersecurity-essentials-for-small-businesses',
    },
    {
      title: 'Mastering the art of time management.',
      excerpt:
        'Forget the apps. The best time-management system is a notebook, a pencil, and an honest conversation.',
      readingTime: '6',
      publishedAt: '2023-04-14',
      collection: { name: 'Personal Development', avatarId: '' },
      creator: 'Emily Johnson',
      slug: 'mastering-the-art-of-time-management',
    },
    {
      cardType: 'stat',
      statValue: '94%',
      statLabel: 'of paywalls bypassed cleanly',
      statDesc:
        'Across the top 200 publications. Failures are usually due to the article not being public yet — not the wall itself.',
      title: '',
      excerpt: '',
      readingTime: '0',
      publishedAt: '2023-01-01',
      creator: '',
      slug: '',
    },
    {
      title: 'The architecture of habit.',
      excerpt:
        'Habits are not built — they are accreted, layer by layer, from things you almost did not bother with.',
      readingTime: '9',
      publishedAt: '2023-04-18',
      collection: { name: 'Psychology', avatarId: '' },
      creator: 'Sarah Wilson',
      slug: 'the-psychology-of-habit-formation',
    },
    {
      title: 'Sustainable tech: small bets, large outcomes.',
      excerpt:
        'A walk through eight startups that aren't trying to save the planet — just to make one slow, dull, important thing 4% more efficient.',
      size: 'tall',
      readingTime: '11',
      publishedAt: '2023-04-20',
      collection: { name: 'Green Technology', avatarId: '' },
      creator: 'David Lee',
      slug: 'sustainable-tech-innovations-for-a-greener-future',
    },
    {
      title: 'The rise of no-code is a story about audience.',
      excerpt:
        'No-code platforms aren't replacing engineers — they're inventing a new kind of builder, and the demographics are surprising.',
      readingTime: '7',
      publishedAt: '2023-04-24',
      collection: { name: 'Software', avatarId: '' },
      creator: 'Alex Rodriguez',
      slug: 'the-rise-of-no-code-development',
    },
    {
      title: 'Mindfulness in the digital age.',
      excerpt:
        'Find balance and reduce stress in an increasingly connected world — without quitting anything you love.',
      readingTime: '4',
      publishedAt: '2023-04-22',
      collection: { name: 'Digital Wellness', avatarId: '' },
      creator: 'Lisa Chen',
      slug: 'mindfulness-in-the-digital-age',
    },
    {
      title: 'Why the static site never died.',
      excerpt:
        'Through three platform cycles, plain HTML has outlived every framework that promised to replace it.',
      readingTime: '7',
      publishedAt: '2023-04-26',
      collection: { name: 'Software Trends', avatarId: '' },
      creator: 'Chris Taylor',
      slug: 'the-rise-of-no-code-development-2',
    },
  ];

  const items: BlogPost[] = blogPosts.map((post, index) => ({ ...post, id: index }));
</script>

<svelte:head>
  <title>Freedium — Reading, without the wall.</title>
</svelte:head>

<Header />
<HomeBanner />

<div class="section-head">
  <div class="left">
    <div class="sub">— Recently unlocked by the community</div>
    <h2>What people are reading</h2>
  </div>
  <div class="filter-bar">
    {#each filters as filter}
      <button
        class:on={activeFilter === filter}
        onclick={() => (activeFilter = filter)}
      >
        {filter}
      </button>
    {/each}
  </div>
</div>

<div class="feed">
  <Masonry {items} minColWidth={300} maxColWidth={480} gap={0} animate={false}>
    {#snippet children({ item }: { item: BlogPost })}
      <BlogCard {...item} />
    {/snippet}
  </Masonry>
</div>

<Footer />

<style>
  .section-head {
    max-width: 1240px;
    margin: 80px auto 24px;
    padding: 0 28px 16px;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    border-bottom: 1px solid var(--line);
    flex-wrap: wrap;
  }
  .sub {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin-bottom: 6px;
  }
  h2 {
    font-family: var(--font-serif);
    font-weight: 400;
    font-style: italic;
    font-size: 36px;
    margin: 0;
    letter-spacing: -0.01em;
    color: var(--ink);
  }

  .filter-bar {
    display: flex;
    gap: 4px;
    background: var(--bg-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 3px;
    font-size: 12px;
  }
  .filter-bar button {
    background: transparent;
    border: none;
    color: var(--ink-3);
    padding: 6px 10px;
    border-radius: 5px;
    font-family: var(--font-sans);
    font-size: 12px;
    cursor: pointer;
    transition: color 0.15s, background 0.15s;
  }
  .filter-bar button.on {
    background: var(--bg-3);
    color: var(--ink);
  }
  .filter-bar button:hover:not(.on) { color: var(--ink-2); }

  .feed {
    max-width: 1240px;
    margin: 0 auto;
    padding: 0 28px;
  }
</style>
```

### Step 6.2 — Verify type-check

- [ ] Run: `bun run check`
- Expected: PASS

### Step 6.3 — Verify visually

- [ ] At `http://localhost:5173`:
  - Page title is "Freedium — Reading, without the wall."
  - Section header "What people are reading" in italic serif
  - Filter bar with 5 pills; clicking each one highlights the active pill
  - Feed shows 11 cards: first is featured (wide, "Featured" badge), third is quote card, sixth is stat card
  - All cards have striped placeholder images, serif titles, green accent topics

### Step 6.4 — Commit

```bash
git add src/routes/+page.svelte
git commit -m "feat: add feed section header and synthetic editorial cards"
```

---

## Task 7: Footer redesign

**Files:**
- Modify: `src/lib/elements/Footer.svelte`

### Step 7.1 — Rewrite Footer.svelte

- [ ] Replace the full content of `src/lib/elements/Footer.svelte`:

```svelte
<script lang="ts">
  import SimpleIconsGithub from '~icons/simple-icons/github';
  import SimpleIconsCodeberg from '~icons/simple-icons/codeberg';
  import { Button } from '$lib/components/ui/button/index.js';
</script>

<footer>
  <div class="left">
    By Freedium &amp; <strong>2,140</strong> contributors.
    <span class="built">— made with care.</span>
  </div>

  <nav>
    <a href="/about">About</a>
    <a href="/privacy">Privacy</a>
    <a href="/terms">Terms</a>
    <a href="#">RSS</a>
    <a href="https://github.com/Freedium-cfd" target="_blank" rel="noopener noreferrer">GitHub</a>
    <a href="https://codeberg.org/Freedium-cfd" target="_blank" rel="noopener noreferrer">Codeberg</a>
  </nav>

  <div class="icons">
    <Button
      variant="ghost"
      size="icon"
      href="https://github.com/Freedium-cfd"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="GitHub"
    >
      <SimpleIconsGithub class="size-4" />
    </Button>
    <Button
      variant="ghost"
      size="icon"
      href="https://codeberg.org/Freedium-cfd"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Codeberg"
    >
      <SimpleIconsCodeberg class="size-4" />
    </Button>
  </div>
</footer>

<style>
  footer {
    max-width: 1240px;
    margin: 80px auto 0;
    padding: 28px;
    border-top: 1px solid var(--line);
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--ink-3);
    font-size: 12px;
    flex-wrap: wrap;
    gap: 16px;
  }

  .left { font-family: var(--font-mono); }
  .left strong { color: var(--ink-2); font-weight: 500; }

  .built {
    font-family: var(--font-serif);
    font-style: italic;
    color: var(--ink-3);
  }

  nav {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    justify-content: center;
  }
  nav a {
    color: var(--ink-3);
    text-decoration: none;
    transition: color 0.15s;
  }
  nav a:hover { color: var(--ink); }

  .icons { display: flex; gap: 4px; }
</style>
```

### Step 7.2 — Verify type-check

- [ ] Run: `bun run check`
- Expected: PASS

### Step 7.3 — Verify full page visually

- [ ] At `http://localhost:5173`, check the full page end-to-end:
  - **Header:** "· Freedium" serif italic, green dot, "beta" chip, all buttons present
  - **Hero:** large serif h1, italic lede, styled unlock bar, stats row below
  - **Section head:** "What people are reading" italic serif h2, filter pills
  - **Feed:** 11 cards with correct types — featured (wide + badge), quote card, stat card, standard cards with stripe images
  - **Footer:** mono contributor line, nav links, icon buttons
  - **Dark mode:** toggle the theme — all sections adapt cleanly to warm off-black
  - **Light mode:** warm parchment background, same sage-green accent

### Step 7.4 — Commit

```bash
git add src/lib/elements/Footer.svelte
git commit -m "feat: redesign footer with editorial layout"
```

---

## Spec Coverage Check

| Spec section | Task |
|---|---|
| Color system (dark + light) | Task 1 |
| Typography (Instrument Serif, JetBrains Mono, Inter) | Task 1 |
| Header re-skin | Task 3 |
| Hero / HomeBanner | Task 4 |
| Unlock bar / UrlBox | Task 4 |
| Blog type CardType | Task 2 |
| BlogCard — all four variants | Task 5 |
| Feed section header | Task 6 |
| Synthetic quote + stat cards | Task 6 |
| Footer | Task 7 |
