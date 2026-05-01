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
    <a href="/rss">RSS</a>
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
