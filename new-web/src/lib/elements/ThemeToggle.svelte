<script lang="ts">
	import { browser } from '$app/environment';
	import { toggleMode, mode } from 'mode-watcher';
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';

	const isDark = $derived(mode.current === 'dark');
</script>

{#if browser}
	<button
		onclick={toggleMode}
		class="theme-toggle"
		data-state={isDark ? 'checked' : 'unchecked'}
		role="switch"
		aria-checked={isDark}
		aria-label="Toggle theme"
		title="Toggle theme"
	>
		<span class="theme-knob">
			{#if isDark}
				<Moon class="size-3" />
			{:else}
				<Sun class="size-3" />
			{/if}
		</span>
	</button>
{:else}
	<!-- SSR placeholder: same footprint, invisible. Avoids hydration flash since the
	     real toggle's state depends on localStorage (only readable client-side). -->
	<span class="theme-toggle-placeholder" aria-hidden="true"></span>
{/if}

<style>
	.theme-toggle {
		position: relative;
		display: inline-flex;
		align-items: center;
		width: 48px;
		height: 28px;
		flex-shrink: 0;
		padding: 0;
		border: 1px solid var(--line);
		border-radius: 999px;
		background: var(--bg-2);
		cursor: pointer;
		transition: background 0.2s, border-color 0.2s;
	}
	.theme-toggle[data-state='checked'] {
		background: var(--accent);
		border-color: var(--accent);
	}
	.theme-toggle:focus-visible {
		outline: 2px solid var(--accent-deep);
		outline-offset: 2px;
	}

	.theme-knob {
		pointer-events: none;
		position: absolute;
		top: 2px;
		left: 2px;
		display: grid;
		place-items: center;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		background: var(--bg);
		color: var(--ink-2);
		transition: transform 0.2s, background 0.2s, color 0.2s;
	}
	.theme-toggle[data-state='checked'] .theme-knob {
		transform: translateX(20px);
		background: oklch(0.18 0.02 145);
		color: var(--accent);
	}

	.theme-toggle-placeholder {
		display: inline-block;
		width: 48px;
		height: 28px;
		flex-shrink: 0;
	}
</style>
