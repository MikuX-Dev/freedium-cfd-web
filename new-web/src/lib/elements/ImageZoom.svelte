<script>
	import mediumZoom from 'medium-zoom';
	import { onDestroy } from 'svelte';

	/** @type {string | undefined} */
	export let src = undefined;
	/** @type {string | undefined} */
	export let alt = undefined;
	/** @type {string | null | undefined} */
	export let zoomSrc = undefined;
	/** Pre-rendered HTML (markdown → HTML in articleRenderer). May be undefined. */
	/** @type {string | undefined} */
	export let caption = undefined;
	/** @type {import('medium-zoom').ZoomOptions | undefined} */
	export let options = undefined;

	/** @type {import('medium-zoom').Zoom | null} */
	let zoom = null;
	let isZoomOpen = false;

	function getZoom() {
		if (zoom === null) {
			const defaultOptions = {
				background: 'rgba(0, 0, 0, 0.8)',
				margin: 24,
			};
			zoom = mediumZoom({ ...defaultOptions, ...options });
			zoom.on('open', () => { isZoomOpen = true; });
			zoom.on('close', () => { isZoomOpen = false; });
		}
		return zoom;
	}

	/** @param {HTMLImageElement} image */
	function attachZoom(image) {
		const zoom = getZoom();
		zoom.attach(image);

		return {
			/** @param {import('medium-zoom').ZoomOptions} newOptions */
			update(newOptions) {
				zoom.update(newOptions);
			},
			destroy() {
				zoom.detach();
			}
		};
	}

	onDestroy(() => {
		isZoomOpen = false;
	});
</script>

{#if caption}
	<figure class="image-zoom-figure">
		<img {src} {alt} data-zoom-src={zoomSrc} {...$$restProps} use:attachZoom />
		<figcaption class="image-zoom-caption">{@html caption}</figcaption>
	</figure>
{:else}
	<img {src} {alt} data-zoom-src={zoomSrc} {...$$restProps} use:attachZoom />
{/if}

{#if isZoomOpen && caption}
	<div class="image-zoom-overlay-caption">{@html caption}</div>
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
	.image-zoom-overlay-caption {
		position: fixed;
		bottom: 40px;
		left: 50%;
		transform: translateX(-50%);
		color: white;
		font-size: 16px;
		font-style: italic;
		text-align: center;
		max-width: 80%;
		padding: 10px 20px;
		background-color: rgba(0, 0, 0, 0.7);
		border-radius: 8px;
		z-index: 9999;
		pointer-events: none;
	}
</style>
