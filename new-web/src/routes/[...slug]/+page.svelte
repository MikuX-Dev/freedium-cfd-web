<script lang="ts">
	import ArticlePage from '$lib/elements/ArticlePage.svelte';
	import ArticlePageSkeleton from '$lib/elements/ArticlePageSkeleton.svelte';

	let { data } = $props();
</script>

{#await data.streamed}
	<ArticlePageSkeleton slug={data.slug} />
{:then result}
	{@const articleData = {
		slug: data.slug,
		loading: false,
		content: result.html,
		markdown: result.markdown,
		article: result.article,
		error: result.error,
		get cacheStatus() { return result.cacheStatus ?? 'miss'; },
		get renderTimeMs() { return result.renderTimeMs ?? 0; },
	}}
	<ArticlePage data={articleData} />
{:catch err}
	<ArticlePage data={{
		slug: data.slug,
		loading: false,
		content: null,
		markdown: null,
		article: null,
		error: { status: 500, message: (err as Error)?.message ?? 'Render failed', code: 'RENDER_ERROR' },
	}} />
{/await}
