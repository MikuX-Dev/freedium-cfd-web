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
