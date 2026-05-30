<script lang="ts">
  import { page } from '$app/state';
  import Header from '$lib/elements/Header.svelte';
  import Footer from '$lib/elements/Footer.svelte';
  import UrlBox from '$lib/elements/UrlBox.svelte';

  const status = $derived(page.status);
  const is404 = $derived(status === 404);
  const message = $derived(page.error?.message ?? '');

  const headline = $derived(
    is404 ? 'This page slipped past the wall.' : 'Something came apart.'
  );
  const sub = $derived(
    is404
      ? "We couldn't find that page. The article may have moved — or you can unlock a fresh one below."
      : 'An unexpected error occurred while loading this page. It may be temporary.'
  );
</script>

<svelte:head>
  <title>{status} — Freedium</title>
  <meta name="robots" content="noindex" />
</svelte:head>

<Header />

<main class="err">
  <div class="eyebrow">— error {status}</div>
  <div class="big">{status}</div>
  <h1>{headline}</h1>
  <p class="sub">{sub}</p>

  {#if is404}
    <div class="box">
      <UrlBox />
    </div>
  {/if}

  <div class="actions">
    <a href="/" class="btn primary">Return home</a>
    {#if !is404}
      <button type="button" class="btn ghost" onclick={() => location.reload()}>
        Try again
      </button>
    {/if}
  </div>

  {#if message && import.meta.env.DEV}
    <pre class="detail">{message}</pre>
  {/if}
</main>

<Footer />

<style>
  .err {
    max-width: 720px;
    margin: 90px auto 110px;
    padding: 0 28px;
    text-align: center;
  }
  .eyebrow {
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin-bottom: 14px;
  }
  .big {
    font-family: var(--font-serif);
    font-style: italic;
    font-size: clamp(96px, 22vw, 180px);
    line-height: 0.9;
    color: var(--accent);
    letter-spacing: -0.02em;
    margin-bottom: 10px;
  }
  h1 {
    font-family: var(--font-serif);
    font-weight: 400;
    font-style: italic;
    font-size: clamp(28px, 5vw, 40px);
    letter-spacing: -0.01em;
    color: var(--ink);
    margin: 0 0 14px;
    text-wrap: balance;
  }
  .sub {
    font-size: 15px;
    line-height: 1.6;
    color: var(--ink-3);
    max-width: 520px;
    margin: 0 auto 32px;
  }
  .box {
    margin: 0 auto 32px;
  }
  .actions {
    display: flex;
    gap: 12px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    padding: 10px 20px;
    border-radius: 8px;
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    border: 1px solid var(--line);
    transition: filter 0.15s, border-color 0.15s, color 0.15s;
  }
  .btn.primary {
    background: var(--accent);
    color: oklch(0.18 0.02 145);
    border-color: transparent;
  }
  .btn.primary:hover { filter: brightness(1.08); }
  .btn.ghost {
    background: transparent;
    color: var(--ink-2);
  }
  .btn.ghost:hover { color: var(--ink); border-color: var(--line-2); }
  .detail {
    margin: 28px auto 0;
    max-width: 640px;
    text-align: left;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--ink-3);
    background: var(--bg-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
</style>
