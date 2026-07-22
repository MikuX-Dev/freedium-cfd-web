<script lang="ts">
	import '../app.css';
	import { Toaster } from '$lib/components/ui/sonner';
	import { ModeWatcher } from 'mode-watcher';
	import ProgressOverlay from '$lib/elements/ProgressOverlay.svelte';
	import type { Snippet } from 'svelte';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	onMount(() => {
		toast.info('Freedium has been updated!', {
			description: 'Found a problem? Join our Discord or open a GitHub issue.',
			duration: 8000,
			action: {
				label: 'Discord',
				onClick: () => window.open('https://discord.gg/dAxCuG9nYM', '_blank')
			}
		});
		toast.info('6 new sources supported!', {
			description: 'Paste any paywalled article — Medium, NYT, Washington Post, Bloomberg, Reuters, or The Economist.',
			duration: 8000
		});
	});
</script>

<ModeWatcher disableTransitions={false} />
<div class="flex flex-col min-h-screen transition-all duration-200 ease-in-out">
	<ProgressOverlay />
	<Toaster position="top-right" expand={true} />
	{@render children()}
</div>
