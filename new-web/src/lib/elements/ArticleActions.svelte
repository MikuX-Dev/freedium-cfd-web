<script lang="ts">
	import HeroiconsArrowLeft20Solid from '~icons/heroicons/arrow-left-20-solid';
	import HeroiconsArrowTopRightOnSquare20Solid from '~icons/heroicons/arrow-top-right-on-square-20-solid';
	import HeroiconsShare20Solid from '~icons/heroicons/share-20-solid';

	interface Props {
		originalUrl?: string | null;
		title?: string;
	}

	let { originalUrl = null, title = 'Freedium' }: Props = $props();

	let shareFeedback = $state<'idle' | 'copied'>('idle');

	async function shareArticle() {
		if (typeof window === 'undefined') return;
		const url = window.location.href;
		const payload = { title, url };
		if (navigator.share) {
			try {
				await navigator.share(payload);
				return;
			} catch (err) {
				if ((err as DOMException)?.name === 'AbortError') return;
			}
		}
		try {
			await navigator.clipboard.writeText(url);
			shareFeedback = 'copied';
			setTimeout(() => { shareFeedback = 'idle'; }, 1500);
		} catch {
			// Clipboard blocked — best-effort, no further fallback.
		}
	}

	const buttonClass =
		'flex items-center justify-center transition bg-white rounded-full shadow-md text-primary hover:text-primary/90 size-8 shadow-zinc-800/5 ring-1 ring-zinc-900/5 dark:border dark:border-zinc-700/50 dark:bg-zinc-800 dark:ring-0 dark:ring-white/10 dark:hover:border-zinc-700 dark:hover:ring-white/20';
</script>

<nav class="flex items-center gap-2 p-4">
	<button
		type="button"
		aria-label="Go back"
		title="Go back"
		class={buttonClass}
		onclick={() => window.history.back()}
	>
		<HeroiconsArrowLeft20Solid class="size-5" />
	</button>
	<div class="flex items-center gap-2 ml-auto">
		<button
			type="button"
			aria-label={shareFeedback === 'copied' ? 'Link copied' : 'Share article'}
			title={shareFeedback === 'copied' ? 'Link copied' : 'Share article'}
			class={buttonClass}
			onclick={shareArticle}
		>
			<HeroiconsShare20Solid class="size-5" />
		</button>
		{#if originalUrl}
			<a
				href={originalUrl}
				target="_blank"
				rel="noopener noreferrer"
				aria-label="Open original article"
				title="Open original article"
				class={buttonClass}
			>
				<HeroiconsArrowTopRightOnSquare20Solid class="size-5" />
			</a>
		{/if}
	</div>
</nav>
