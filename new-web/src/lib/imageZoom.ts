/**
 * Lightweight, dependency-free image lightbox with prev/next navigation.
 *
 * Replaces medium-zoom. Opens INSTANTLY with the resolution the browser
 * already decoded (`currentSrc`, 700/2000px in cache), then quietly upgrades
 * to the 2000px variant in the background — never the 4000px, never blocking,
 * so it can't hang. Arrows (and ← → keys) cycle through every zoomable image
 * in the article; scroll / Esc / click closes.
 */

let overlay: HTMLDivElement | null = null;
let overlayImg: HTMLImageElement | null = null;
let overlayCaption: HTMLDivElement | null = null;
let prevBtn: HTMLButtonElement | null = null;
let nextBtn: HTMLButtonElement | null = null;

// Ordered list of images the lightbox can page through, + current position.
let gallery: HTMLImageElement[] = [];
let currentIndex = -1;

const STYLE_ID = "fz-lightbox-style";
const CSS = `
.fz-lightbox{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;
justify-content:center;background:rgba(0,0,0,.92);cursor:zoom-out;padding:24px;
opacity:0;transition:opacity .15s ease;}
.fz-lightbox.fz-open{opacity:1;}
.fz-lightbox[hidden]{display:none;}
.fz-lightbox-img{max-width:100%;max-height:100%;object-fit:contain;
box-shadow:0 8px 50px rgba(0,0,0,.5);border-radius:2px;}
.fz-lightbox-caption{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);
color:rgba(255,255,255,.82);font-size:13px;line-height:1.5;max-width:min(640px,84%);
text-align:center;padding:6px 16px;background:rgba(20,20,20,.45);
backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);border-radius:999px;
pointer-events:auto;}
.fz-lightbox-caption:empty{display:none;}
.fz-lightbox-caption a{color:#fff;text-decoration:underline;text-underline-offset:2px;
text-decoration-thickness:1px;}
.fz-lightbox-caption a:hover{text-decoration-color:rgba(255,255,255,.6);}
.fz-nav{position:fixed;top:50%;transform:translateY(-50%);z-index:10000;display:flex;
align-items:center;justify-content:center;width:46px;height:46px;border:none;
border-radius:50%;background:rgba(0,0,0,.45);color:#fff;cursor:pointer;
backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);transition:background .15s;}
.fz-nav:hover{background:rgba(0,0,0,.72);}
.fz-prev{left:16px;}
.fz-next{right:16px;}
.fz-nav svg{width:24px;height:24px;}
.fz-nav[hidden]{display:none;}
@media(max-width:560px){.fz-nav{width:40px;height:40px;left:8px;}.fz-next{right:8px;}}
`;

const CHEVRON_LEFT =
	'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>';
const CHEVRON_RIGHT =
	'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>';

function injectStyleOnce(): void {
	if (document.getElementById(STYLE_ID)) return;
	const el = document.createElement("style");
	el.id = STYLE_ID;
	el.textContent = CSS;
	document.head.appendChild(el);
}

function ensureOverlay(): void {
	if (overlay) return;
	injectStyleOnce();
	overlay = document.createElement("div");
	overlay.className = "fz-lightbox";
	overlay.hidden = true;
	overlay.setAttribute("role", "dialog");
	overlay.setAttribute("aria-modal", "true");

	overlayImg = document.createElement("img");
	overlayImg.className = "fz-lightbox-img";
	overlayImg.alt = "";

	overlayCaption = document.createElement("div");
	overlayCaption.className = "fz-lightbox-caption";

	prevBtn = document.createElement("button");
	prevBtn.type = "button";
	prevBtn.className = "fz-nav fz-prev";
	prevBtn.setAttribute("aria-label", "Previous image");
	prevBtn.innerHTML = CHEVRON_LEFT;
	prevBtn.addEventListener("click", (e) => {
		e.stopPropagation(); // don't close
		navigate(-1);
	});

	nextBtn = document.createElement("button");
	nextBtn.type = "button";
	nextBtn.className = "fz-nav fz-next";
	nextBtn.setAttribute("aria-label", "Next image");
	nextBtn.innerHTML = CHEVRON_RIGHT;
	nextBtn.addEventListener("click", (e) => {
		e.stopPropagation();
		navigate(1);
	});

	overlay.append(overlayImg, overlayCaption, prevBtn, nextBtn);
	overlay.addEventListener("click", close);
	document.body.appendChild(overlay);
}

function onKey(e: KeyboardEvent): void {
	if (e.key === "Escape") close();
	else if (e.key === "ArrowLeft") navigate(-1);
	else if (e.key === "ArrowRight") navigate(1);
}

// Any scroll gesture while open closes the lightbox (medium-zoom feel).
let scrollClose: (() => void) | null = null;

/** Derive the 2000px variant of an /img proxy URL, if applicable. */
function highResVariant(src: string): string | null {
	const m = src.match(/\/img\/\d+\/(.+)$/);
	return m ? `/img/2000/${m[1]}` : null;
}

/** Load an image's content into the overlay: instant currentSrc, async 2000px
 * upgrade, caption. No layout animation (used for open + navigation). */
function renderImage(img: HTMLImageElement): void {
	if (!overlayImg || !overlayCaption) return;
	const loaded = img.currentSrc || img.src;
	overlayImg.src = loaded;
	overlayImg.alt = img.alt || "";

	const hi = highResVariant(img.dataset.zoomSrc || img.src || "");
	if (hi && hi !== loaded) {
		const pre = new Image();
		pre.onload = () => {
			// Only apply if we're still showing this image (guards fast paging).
			if (overlay && !overlay.hidden && overlayImg && gallery[currentIndex] === img) {
				overlayImg.src = hi;
			}
		};
		pre.src = hi;
	}

	// data-caption is already rendered HTML (server-side) — just display it.
	overlayCaption.innerHTML = img.getAttribute("data-caption") || "";
}

/** Show/hide the arrows depending on how many images are in the gallery. */
function updateNav(): void {
	const many = gallery.length > 1 && currentIndex >= 0;
	if (prevBtn) prevBtn.hidden = !many;
	if (nextBtn) nextBtn.hidden = !many;
}

/** Step to the previous/next image (cyclic) with a directional slide+fade. */
function navigate(delta: number): void {
	if (!overlay || overlay.hidden || gallery.length < 2 || currentIndex < 0 || !overlayImg)
		return;
	currentIndex = (currentIndex + delta + gallery.length) % gallery.length;
	renderImage(gallery[currentIndex]);

	// Single-phase: swap instantly, then slide the new image in from the side
	// it's coming from (next → from the right, prev → from the left) with a
	// quick fade. No timers, so rapid paging stays snappy and never races.
	const img = overlayImg;
	img.style.transition = "none";
	img.style.transform = `translateX(${delta * 44}px)`;
	img.style.opacity = "0.25";
	void img.offsetWidth; // flush the start state
	requestAnimationFrame(() => {
		img.style.transition = "transform .22s cubic-bezier(.2,0,.2,1), opacity .2s ease";
		img.style.transform = "none";
		img.style.opacity = "1";
	});
}

/** Open the lightbox for an image — instant, no blocking network. */
export function openLightbox(img: HTMLImageElement): void {
	ensureOverlay();
	if (!overlay || !overlayImg || !overlayCaption) return;

	// Build the gallery from every zoomable image in document order so the
	// arrows can page through them (cover + body images carry data-zoom-src).
	gallery = Array.from(document.querySelectorAll<HTMLImageElement>("img[data-zoom-src]"));
	currentIndex = gallery.indexOf(img);
	updateNav();

	renderImage(img);

	// Reveal at final (centered, contained) layout, transition off, so we
	// can measure where the image ends up. Reset opacity in case a previous
	// navigation animation left it mid-flight.
	overlay.hidden = false;
	overlayImg.style.transition = "none";
	overlayImg.style.transform = "none";
	overlayImg.style.opacity = "1";
	const finalRect = overlayImg.getBoundingClientRect();
	const srcRect = img.getBoundingClientRect();

	// FLIP: place the overlay image over the clicked thumbnail, then animate
	// it to its final centered position so it "grows" out of the page.
	if (finalRect.width > 0 && srcRect.width > 0) {
		const scale = srcRect.width / finalRect.width;
		const dx =
			srcRect.left + srcRect.width / 2 - (finalRect.left + finalRect.width / 2);
		const dy =
			srcRect.top + srcRect.height / 2 - (finalRect.top + finalRect.height / 2);
		overlayImg.style.transformOrigin = "center center";
		overlayImg.style.transform = `translate(${dx}px, ${dy}px) scale(${scale})`;
		void overlayImg.offsetWidth; // flush the start state
		requestAnimationFrame(() => {
			if (!overlayImg) return;
			overlayImg.style.transition = "transform .28s cubic-bezier(.2,0,.2,1)";
			overlayImg.style.transform = "none";
		});
	}

	requestAnimationFrame(() => overlay?.classList.add("fz-open"));
	document.body.style.overflow = "hidden";
	document.addEventListener("keydown", onKey);

	// Close on any scroll/wheel/touch-move while open.
	scrollClose = () => close();
	window.addEventListener("wheel", scrollClose, { passive: true });
	window.addEventListener("touchmove", scrollClose, { passive: true });
	window.addEventListener("scroll", scrollClose, { passive: true });
}

function close(): void {
	if (!overlay || overlay.hidden) return;
	overlay.classList.remove("fz-open");
	document.body.style.overflow = "";
	document.removeEventListener("keydown", onKey);
	if (scrollClose) {
		window.removeEventListener("wheel", scrollClose);
		window.removeEventListener("touchmove", scrollClose);
		window.removeEventListener("scroll", scrollClose);
		scrollClose = null;
	}
	// Fade the backdrop out, then hide + reset the image transform.
	const el = overlay;
	const imgEl = overlayImg;
	window.setTimeout(() => {
		el.hidden = true;
		if (imgEl) {
			imgEl.style.transition = "none";
			imgEl.style.transform = "none";
			imgEl.style.opacity = "1";
		}
	}, 160);
}

/** Bind every `.prose-image` in the rendered article to the lightbox. */
export function initializeImageZoom(): void {
	const images = document.querySelectorAll<HTMLImageElement>(".prose-image");
	images.forEach((img) => {
		if (img.dataset.fzBound) return;
		img.dataset.fzBound = "1";
		img.style.cursor = "zoom-in";
		img.addEventListener("click", () => openLightbox(img));
	});
}

export function cleanupImageZoom(): void {
	close();
}
