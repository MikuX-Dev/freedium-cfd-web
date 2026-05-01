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
