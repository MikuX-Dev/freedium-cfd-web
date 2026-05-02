<script lang="ts">
  import UrlBox from './UrlBox.svelte';
</script>

<section class="hero">
  <div class="hero-bg" aria-hidden="true">
    <article class="skeleton sk-1">
      <div class="sk-avatar"></div>
      <div class="sk-title"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </article>
    <article class="skeleton sk-2">
      <div class="sk-avatar"></div>
      <div class="sk-title"></div>
      <div class="sk-line"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </article>
    <article class="skeleton sk-3">
      <div class="sk-avatar"></div>
      <div class="sk-title short"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </article>
    <article class="skeleton sk-4">
      <div class="sk-avatar"></div>
      <div class="sk-title"></div>
      <div class="sk-line"></div>
      <div class="sk-line"></div>
    </article>
    <article class="skeleton sk-5">
      <div class="sk-avatar"></div>
      <div class="sk-title short"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </article>
    <article class="skeleton sk-6">
      <div class="sk-avatar"></div>
      <div class="sk-title"></div>
      <div class="sk-line"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </article>

    <span class="dot dot-1"></span>
    <span class="dot dot-2"></span>
    <span class="dot dot-3"></span>
    <span class="dot dot-4"></span>
    <span class="dot dot-5"></span>
    <span class="dot dot-6"></span>
    <span class="dot dot-7"></span>
    <span class="dot dot-8"></span>
    <span class="dot dot-9"></span>
  </div>

  <div class="hero-content">
    <div class="eyebrow">
      <span class="pulse"></span>
      Open access reader · est. 2023
    </div>
    <h1>Reading, <em>without the wall.</em></h1>
    <p class="lede">Paste any paywalled article link below — Freedium fetches an open, ad-free version you can keep.</p>
    <UrlBox showProtocol={false} />
    <div class="unlock-meta">
      <div class="stat">↳ <strong>1.2M</strong> articles unlocked this month</div>
      <div class="stat">
        <kbd>↵</kbd> to unlock · <kbd>⇧↵</kbd> to save without opening
      </div>
      <div class="stat"><strong>26ms</strong> avg fetch</div>
    </div>
  </div>
</section>

<style>
  .hero {
    position: relative;
    max-width: 980px;
    margin: 0 auto;
    padding: 72px 28px 36px;
    text-align: center;
  }

  .hero-content {
    position: relative;
    z-index: 1;
  }

  /* Decorative drifting article skeletons — pure background ambience.
     No overflow clip and no mask — skeletons render fully. They sit
     behind hero content via z-index and read as ambient through their
     reduced opacity (set on .skeleton itself). */
  .hero-bg {
    position: absolute;
    inset: -40px 0;
    z-index: 0;
    pointer-events: none;
  }

  .skeleton {
    position: absolute;
    width: 220px;
    padding: 14px 16px;
    border: 1px solid var(--line);
    border-radius: 4px;
    background: color-mix(in oklch, var(--bg-2) 70%, transparent);
    text-align: left;
    opacity: 0;
    animation: sk-fade-in 1.4s ease-out forwards, sk-drift 24s ease-in-out infinite;
    will-change: transform, opacity;
  }

  .sk-avatar {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--line);
    margin-bottom: 12px;
  }
  .sk-title {
    height: 10px;
    width: 80%;
    border-radius: 2px;
    background: var(--line);
    margin-bottom: 10px;
  }
  .sk-title.short { width: 55%; }
  .sk-line {
    height: 6px;
    width: 100%;
    border-radius: 2px;
    background: var(--line-2);
    margin-bottom: 6px;
  }
  .sk-line.short { width: 60%; }

  /* Distribute skeletons around the hero edges with varied animation timing. */
  .sk-1 { top: 4%;   left: 2%;  animation-delay: 0s, -2s;   transform: rotate(-3deg); }
  .sk-2 { top: 10%;  right: 4%; animation-delay: 0.2s, -8s; transform: rotate(2deg); }
  .sk-3 { top: 48%;  left: -2%; animation-delay: 0.4s, -14s; transform: rotate(1deg); }
  .sk-4 { top: 52%;  right: 0%; animation-delay: 0.6s, -5s;  transform: rotate(-2deg); }
  .sk-5 { bottom: 6%; left: 6%;  animation-delay: 0.8s, -11s; transform: rotate(2deg); }
  .sk-6 { bottom: 2%; right: 8%; animation-delay: 1s, -17s;  transform: rotate(-1deg); }

  /* Each skeleton uses two animations: fade-in (once) + drift (loop).
     Keep fade-in additive so the rotate baseline survives the drift. */
  @keyframes sk-fade-in {
    from { opacity: 0; }
    to   { opacity: 0.35; }
  }
  @keyframes sk-drift {
    0%, 100% { translate: 0 0; }
    50%      { translate: 0 -14px; }
  }

  /* Subtle shimmer pulse on the title bar to suggest "loading" articles. */
  .sk-title {
    background: linear-gradient(
      90deg,
      var(--line) 0%,
      var(--line-2) 50%,
      var(--line) 100%
    );
    background-size: 200% 100%;
    animation: sk-shimmer 6s linear infinite;
  }
  .sk-1 .sk-title { animation-delay: -1s; }
  .sk-2 .sk-title { animation-delay: -3s; }
  .sk-3 .sk-title { animation-delay: -5s; }
  .sk-4 .sk-title { animation-delay: -2s; }
  .sk-5 .sk-title { animation-delay: -4s; }
  .sk-6 .sk-title { animation-delay: -6s; }
  @keyframes sk-shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Pulsing accent dots scattered across the background — echoes the
     eyebrow pulse to suggest a live network of articles being unlocked. */
  .dot {
    position: absolute;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--accent);
    opacity: 0;
    animation: dot-pulse 4s ease-out infinite;
  }
  .dot::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 1px solid var(--accent);
    animation: dot-ring 4s ease-out infinite;
  }

  /* Distribute dots away from the dense skeleton zones, on a soft scatter. */
  .dot-1 { top: 18%; left: 22%; animation-delay: 0s; }
  .dot-1::after { animation-delay: 0s; }
  .dot-2 { top: 8%;  left: 70%; animation-delay: 0.6s; }
  .dot-2::after { animation-delay: 0.6s; }
  .dot-3 { top: 38%; left: 12%; animation-delay: 1.2s; }
  .dot-3::after { animation-delay: 1.2s; }
  .dot-4 { top: 30%; right: 18%; animation-delay: 1.8s; }
  .dot-4::after { animation-delay: 1.8s; }
  .dot-5 { top: 62%; left: 28%; animation-delay: 2.4s; }
  .dot-5::after { animation-delay: 2.4s; }
  .dot-6 { top: 70%; right: 24%; animation-delay: 3s; }
  .dot-6::after { animation-delay: 3s; }
  .dot-7 { bottom: 14%; left: 40%; animation-delay: 0.3s; }
  .dot-7::after { animation-delay: 0.3s; }
  .dot-8 { top: 24%; left: 48%; animation-delay: 1.5s; }
  .dot-8::after { animation-delay: 1.5s; }
  .dot-9 { bottom: 22%; right: 44%; animation-delay: 2.7s; }
  .dot-9::after { animation-delay: 2.7s; }

  @keyframes dot-pulse {
    0%   { opacity: 0; }
    20%  { opacity: 0.7; }
    60%  { opacity: 0.4; }
    100% { opacity: 0; }
  }
  @keyframes dot-ring {
    0%   { transform: scale(1);   opacity: 0.6; }
    100% { transform: scale(5);   opacity: 0; }
  }

  /* Hide skeletons on narrow viewports to avoid crowding the hero text. */
  @media (max-width: 1180px) {
    .hero-bg { display: none; }
  }

  /* Honor reduced-motion preferences: snap to visible without animation. */
  @media (prefers-reduced-motion: reduce) {
    .skeleton {
      animation: none;
      opacity: 0.4;
    }
    .sk-title { animation: none; }
    .dot, .dot::after { animation: none; }
    .dot { opacity: 0.4; }
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
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    column-gap: 24px;
    row-gap: 8px;
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

  @media (max-width: 820px) {
    .unlock-meta {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }
  }
</style>
