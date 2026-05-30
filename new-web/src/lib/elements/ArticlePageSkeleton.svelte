<script lang="ts">
	import Header from '$lib/elements/Header.svelte';
	import Footer from '$lib/elements/Footer.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import './ArticlePage.css';

	interface Props {
		slug?: string | null;
	}

	let { slug }: Props = $props();
</script>

<Header />
<div class="article-page-container">
	<article class="overflow-hidden bg-white rounded-lg shadow-lg dark:bg-zinc-900">
		<!-- hero image placeholder -->
		<Skeleton class="w-full h-96" />

		<div class="p-6 bg-gray-50 dark:bg-zinc-800">
			<!-- category / reading time -->
			<Skeleton class="w-32 h-4 mb-2" />
			<!-- title -->
			<Skeleton class="w-full h-10 mb-4" />
			<!-- author row -->
			<div class="flex items-center">
				<Skeleton class="w-12 h-12 mr-4 rounded-full" />
				<div class="space-y-2">
					<Skeleton class="w-40 h-4" />
					<Skeleton class="w-32 h-4" />
				</div>
			</div>
		</div>

		<div class="p-6">
			<div class="space-y-4">
				<Skeleton class="w-full h-4" />
				<Skeleton class="w-full h-4" />
				<Skeleton class="w-3/4 h-4" />
				<Skeleton class="w-5/6 h-4" />
				<Skeleton class="w-full h-4" />
				<Skeleton class="w-2/3 h-4" />
				<Skeleton class="w-full h-4" />
				<Skeleton class="w-4/5 h-4" />
				<Skeleton class="w-full h-4" />
				<Skeleton class="w-3/4 h-4" />
			</div>
		</div>
	</article>
</div>
<Footer />
