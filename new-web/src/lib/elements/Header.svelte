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
    // While the mobile menu is open it lives inside this nav — keep the
    // header pinned so scrolling (e.g. to reach menu items) can't slide the
    // whole thing (and the open menu) off-screen.
    if (isNavOpen) {
      isHeaderVisible = true;
      lastScrollY = window.scrollY;
      return;
    }
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

  const toggleNav = () => {
    isNavOpen = !isNavOpen;
    if (isNavOpen) isHeaderVisible = true; // reveal the header when opening the menu
  };
  const toggleSearch = () => { isSearchOpen = !isSearchOpen; };
</script>

<ProgressLine />

<nav
  id="header"
  class="header-nav"
  style="transform: translateY({isHeaderVisible ? '0' : '-100%'})"
>
  <div class="container flex items-center justify-between h-14 px-4 mx-auto">
    <!-- Logo -->
    <a class="brand-link" href="/">
      <span class="brand-mark"><span class="brand-dot">·</span> Freedium</span>
      <span class="brand-tag"><sup>beta</sup></span>
    </a>

    <!-- Desktop Navigation -->
    <div class="items-center hidden gap-1 md:flex">
      <!-- <Button variant="ghost" size="icon" onclick={toggleSearch} title="Search">
        <Search class="size-5" />
      </Button> -->

      <ExtensionsButton />

      <ReportProblem compact={true} />

      <div class="w-px h-5 mx-1" style="background: var(--line)"></div>

      <ThemeToggle />

      <div class="w-px h-5 mx-1" style="background: var(--line)"></div>

      <div class="flex items-center gap-0.5">
        <PayButtons name="Ko-fi" url="https://ko-fi.com/zhymabekroman" icon={TeenyiconsCupSolid} showLabel={false} />
        <PayButtons name="Liberapay" url="https://liberapay.com/ZhymabekRoman/" icon={SimpleIconsLiberapay} showLabel={false} />
        <PayButtons name="Discord" url="https://discord.gg/dAxCuG9nYM" icon={SimpleIconsDiscord} showLabel={false} />
      </div>

      <!--
      <Button size="sm" class="ml-2 gap-1.5">
        <Plus class="size-4" />
        <span>Submit link</span>
      </Button>
      -->
    </div>

    <!-- Mobile Navigation -->
    <div class="flex items-center gap-1 md:hidden">
      <!-- <Button variant="ghost" size="icon" onclick={toggleSearch} title="Search">
        <Search class="size-5" />
      </Button> -->
      <ReportProblem compact={true} />
      <ThemeToggle />
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
        <!--
        <Button class="w-full gap-2">
          <Plus class="size-4" />
          <span>Submit link</span>
        </Button>
        -->

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

<!-- <SearchDialog bind:open={isSearchOpen} /> -->

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
    font-family: var(--font-serif);
    font-size: 13px;
    font-style: italic;
    color: var(--ink-4);
    margin-left: -4px;
    align-self: flex-start;
    line-height: 1;
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
