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

  const palettes = ['ph-warm', 'ph-cool', 'ph-green', 'ph-rose', 'ph-violet', 'ph-sand'];
  const phTags = [
    'editorial photo · 21:10', 'forest path', 'cliff coastline',
    'desk · still life', 'mushroom · macro', 'solar field · dusk', 'snow peaks'
  ];
  const avClasses = ['av-1', 'av-2', 'av-3', 'av-4', 'av-5', 'av-6'];

  const isFeatured = $derived(cardType === 'featured');
  const phClass = $derived(palettes[id % palettes.length]);
  const phTag = $derived(phTags[id % phTags.length]);
  const thumbClass = $derived(
    size === 'tall' ? 'thumb tall'
      : (size === 'wide' || isFeatured) ? 'thumb wide'
      : 'thumb'
  );
  const avClass = $derived(avClasses[id % avClasses.length]);

  function initials(name: string): string {
    return name.split(' ').map((w) => w[0] ?? '').join('').slice(0, 2).toUpperCase();
  }

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
