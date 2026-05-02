<script lang="ts">
  import Header from '$lib/elements/Header.svelte';
  import HomeBanner from '$lib/elements/HomeBanner.svelte';
  import BlogCard from '$lib/elements/BlogCard.svelte';
  import Footer from '$lib/elements/Footer.svelte';
  import type { BlogPost } from '$lib/types';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  let activeFilter = $state('Latest');
  const filters = ['Latest', 'Trending', 'This week', 'Long reads', 'Following'];

  // Fallback seed: shown only when the backend has not yet recorded any
  // unlocks. Acts as visual scaffolding so first-run / dev-without-backend
  // still renders a populated page.
  const seedPosts: Omit<BlogPost, 'id'>[] = [
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
        'A walk through eight startups that aren’t trying to save the planet — just to make one slow, dull, important thing 4% more efficient.',
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
        'No-code platforms aren’t replacing engineers — they’re inventing a new kind of builder, and the demographics are surprising.',
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

  const seedItems: BlogPost[] = seedPosts.map((post, index) => ({ ...post, id: index }));
  const items = $derived<BlogPost[]>(
    data.items.length > 0 ? data.items : seedItems,
  );
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
  {#each items as item (item.id)}
    <BlogCard {...item} />
  {/each}
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
    columns: 3;
    column-gap: 24px;
  }
  @media (max-width: 1000px) { .feed { columns: 2; } }
  @media (max-width: 640px)  { .feed { columns: 1; } }
</style>
