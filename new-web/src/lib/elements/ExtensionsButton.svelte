<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import BookmarkButton from './BookmarkButton.svelte';
	import MdiPuzzle from '~icons/mdi/puzzle';
	import MdiFirefox from '~icons/mdi/firefox';
	import HeroiconsOutlineExternalLink from '~icons/heroicons-outline/external-link';
	import MdiGoogleChrome from '~icons/mdi/google-chrome';
	import MdiAppleSafari from '~icons/mdi/apple-safari';
	import MdiScriptText from '~icons/mdi/script-text';
</script>

<DropdownMenu.Root>
	<DropdownMenu.Trigger>
		{#snippet child({ props })}
			<Button
				{...props}
				variant="ghost"
				class="size-9 p-0 text-zinc-600 dark:text-zinc-300 hover:text-primary dark:hover:text-primary transition-colors"
				title="Browser extensions"
			>
				<MdiPuzzle class="size-5 shrink-0" />
			</Button>
		{/snippet}
	</DropdownMenu.Trigger>

	<DropdownMenu.Content class="ext-menu" sideOffset={6}>
		<div class="ext-eyebrow">Browser &amp; App Extensions</div>

		<p class="ext-note">
			These solutions are not developed or controlled by the Freedium team —
			use at your own risk. Freedium is not responsible for any damages or
			losses caused by them.
		</p>

		<DropdownMenu.Separator class="ext-sep" />

		<DropdownMenu.Group>
			<DropdownMenu.Item class="ext-item">
				<MdiFirefox class="size-4 shrink-0" />
				<span class="ext-label">Firefox</span>
				<HeroiconsOutlineExternalLink class="size-3.5 ext-ext shrink-0" />
			</DropdownMenu.Item>

			<DropdownMenu.Item class="ext-item">
				<MdiGoogleChrome class="size-4 shrink-0" />
				<span class="ext-label">Chrome</span>
				<HeroiconsOutlineExternalLink class="size-3.5 ext-ext shrink-0" />
			</DropdownMenu.Item>
			<DropdownMenu.Item class="ext-item">
				<a
					class="ext-link"
					href="https://www.icloud.com/shortcuts/046dddefef2e47e2aebc20e6c81c87e1"
					target="_blank"
					rel="noopener noreferrer"
				>
					<MdiAppleSafari class="size-4 shrink-0" />
					<span class="ext-label">Safari / iOS Shortcut</span>
					<HeroiconsOutlineExternalLink class="size-3.5 ext-ext shrink-0" />
				</a>
				<span class="ext-credit">by _08vishal</span>
			</DropdownMenu.Item>
		</DropdownMenu.Group>

		<DropdownMenu.Separator class="ext-sep" />

		<DropdownMenu.Item class="ext-item">
			<a
				class="ext-link"
				href="https://gist.github.com/mathix420/e0604ab0e916622972372711d2829555"
				target="_blank"
				rel="noopener noreferrer"
			>
				<MdiScriptText class="size-4 shrink-0" />
				<span class="ext-label">Userscript — Medium only</span>
				<HeroiconsOutlineExternalLink class="size-3.5 ext-ext shrink-0" />
			</a>
		</DropdownMenu.Item>

		<DropdownMenu.Separator class="ext-sep" />

		<BookmarkButton />
	</DropdownMenu.Content>
</DropdownMenu.Root>

<style>
	:global(.ext-menu) {
		width: 248px;
		padding: 6px;
		background: var(--bg-2);
		border: 1px solid var(--line);
		color: var(--ink-2);
	}

	.ext-eyebrow {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--ink-3);
		padding: 8px 10px 6px;
	}

	.ext-note {
		margin: 0;
		padding: 0 10px 8px;
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 12.5px;
		line-height: 1.45;
		color: var(--ink-3);
	}

	:global(.ext-sep) {
		margin: 4px 0 !important;
		background: var(--line) !important;
	}

	:global(.ext-item) {
		display: flex !important;
		align-items: center;
		gap: 10px;
		padding: 8px 10px !important;
		border-radius: 6px;
		font-family: var(--font-sans);
		font-size: 13px;
		color: var(--ink) !important;
		cursor: pointer;
	}
	:global(.ext-item:hover),
	:global(.ext-item[data-highlighted]) {
		background: var(--bg-3) !important;
	}

	:global(.ext-label) {
		flex: 1;
		min-width: 0;
		text-align: left;
	}

	:global(.ext-ext) {
		color: var(--ink-3);
	}

	:global(.ext-credit) {
		display: block;
		font-size: 10px;
		color: var(--ink-4);
		padding-left: 26px;
		margin-top: -4px;
	}

	:global(.ext-link) {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		text-decoration: none;
		color: inherit;
	}
</style>
