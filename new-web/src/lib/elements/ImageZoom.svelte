<script>
	import { openLightbox } from '$lib/imageZoom';

	/** @type {string | undefined} */
	export let src = undefined;
	/** @type {string | undefined} */
	export let alt = undefined;
	/** @type {string | null | undefined} */
	export let zoomSrc = undefined;
	/** Pre-rendered HTML (markdown → HTML in articleRenderer). May be undefined. */
	/** @type {string | undefined} */
	export let caption = undefined;

	/** @param {MouseEvent} e */
	function open(e) {
		const img = e.currentTarget;
		if (img instanceof HTMLImageElement) openLightbox(img);
	}
</script>

{#if caption}
	<figure class="image-zoom-figure">
		<img
			{src}
			{alt}
			data-zoom-src={zoomSrc}
			{...$$restProps}
			style="cursor: zoom-in"
			on:click={open}
		/>
		<figcaption class="image-zoom-caption">{@html caption}</figcaption>
	</figure>
{:else}
	<img
		{src}
		{alt}
		data-zoom-src={zoomSrc}
		{...$$restProps}
		style="cursor: zoom-in"
		on:click={open}
	/>
{/if}

<style>
	.image-zoom-figure {
		margin: 0;
	}
	.image-zoom-caption {
		margin-top: 0.75rem;
		padding: 0 1rem;
		font-size: 0.875rem;
		font-style: italic;
		color: rgb(107 114 128);
		text-align: center;
	}
	:global(.dark) .image-zoom-caption {
		color: rgb(209 213 219);
	}
</style>
