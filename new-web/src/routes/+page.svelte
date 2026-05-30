<script lang="ts">
  import Header from '$lib/elements/Header.svelte';
  import HomeBanner from '$lib/elements/HomeBanner.svelte';
  import BlogCard from '$lib/elements/BlogCard.svelte';
  import Footer from '$lib/elements/Footer.svelte';
  import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
  import type { BlogPost } from '$lib/types';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  let activeFilter = $state('Latest');
  const filters = ['Latest', 'Trending', 'This week', 'Long reads', 'Following'];
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

{#await data.streamed}
  <div class="feed">
    {#each Array(6) as _}
      <div class="skeleton-card">
        <Skeleton class="w-full h-48 mb-3 rounded-lg" />
        <Skeleton class="w-3/4 h-4 mb-2" />
        <Skeleton class="w-full h-3 mb-1" />
        <Skeleton class="w-2/3 h-3" />
      </div>
    {/each}
  </div>
{:then result}
  {@const displayItems = (activeFilter === 'Trending' ? result.randomItems : result.items) ?? []}
  {#if result.isFeedEmpty}
    <div class="empty-state">
      <div class="empty-mark">&empty;</div>
      <h3>No recent unlocks yet.</h3>
      <p>Paste an article URL above to unlock the first one — it'll appear here for everyone.</p>
    </div>
  {:else}
    <div class="feed">
      {#each displayItems as item (item.id)}
        <BlogCard {...item} />
      {/each}
    </div>
  {/if}
{:catch}
  <div class="empty-state">
    <div class="empty-mark">&empty;</div>
    <h3>Couldn't load the feed.</h3>
    <p>The backend may be under heavy load. Try refreshing in a moment.</p>
  </div>
{/await}

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
    columns: 3;
    column-gap: 24px;
  }
  @media (max-width: 1000px) { .feed { columns: 2; } }
  @media (max-width: 640px)  { .feed { columns: 1; } }

  .skeleton-card {
    break-inside: avoid;
    margin-bottom: 24px;
    padding: 16px;
    background: var(--bg-2);
    border-radius: 12px;
  }

  .empty-state {
    max-width: 540px;
    margin: 80px auto 120px;
    padding: 0 28px;
    text-align: center;
  }
  .empty-mark {
    font-family: var(--font-serif);
    font-size: 96px;
    line-height: 1;
    color: var(--accent);
    font-style: italic;
    margin-bottom: 16px;
  }
  .empty-state h3 {
    font-family: var(--font-serif);
    font-weight: 400;
    font-style: italic;
    font-size: 32px;
    margin: 0 0 12px;
    color: var(--ink);
    letter-spacing: -0.01em;
  }
  .empty-state p {
    font-size: 14px;
    color: var(--ink-3);
    margin: 0;
    line-height: 1.55;
  }
</style>
