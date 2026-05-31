/**
 * Lightweight, dependency-free image lightbox.
 *
 * Replaces medium-zoom. The old viewer fetched the 4000px `data-zoom-src`
 * variant on click — a multi-MB image pulled cold through the WARP proxy,
 * which made zoom slow / hang. This opens INSTANTLY with the resolution the
 * browser already loaded (`currentSrc`, 700/2000px in cache), then quietly
 * upgrades to the 2000px variant in the background. It never loads 4000px
 * and the upgrade never blocks the open, so it can't hang.
 */

let overlay: HTMLDivElement | null = null;
let overlayImg: HTMLImageElement | null = null;
let overlayCaption: HTMLDivElement | null = null;

const STYLE_ID = "fz-lightbox-style";
const CSS = `
.fz-lightbox{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;
justify-content:center;background:rgba(0,0,0,.92);cursor:zoom-out;padding:24px;
opacity:0;transition:opacity .15s ease;}
.fz-lightbox.fz-open{opacity:1;}
.fz-lightbox[hidden]{display:none;}
.fz-lightbox-img{max-width:100%;max-height:100%;object-fit:contain;
box-shadow:0 8px 50px rgba(0,0,0,.5);border-radius:2px;}
.fz-lightbox-caption{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
color:#fff;font-style:italic;font-size:15px;line-height:1.5;max-width:80%;
text-align:center;padding:8px 16px;background:rgba(0,0,0,.6);border-radius:8px;
pointer-events:none;}
`;

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

	overlay.append(overlayImg, overlayCaption);
	overlay.addEventListener("click", close);
	document.body.appendChild(overlay);
}

function onKey(e: KeyboardEvent): void {
	if (e.key === "Escape") close();
}

// Any scroll gesture while open closes the lightbox (medium-zoom feel).
let scrollClose: (() => void) | null = null;

/** Derive the 2000px variant of an /img proxy URL, if applicable. */
function highResVariant(src: string): string | null {
	const m = src.match(/\/img\/\d+\/(.+)$/);
	return m ? `/img/2000/${m[1]}` : null;
}

/** Open the lightbox for an image — instant, no blocking network. */
export function openLightbox(img: HTMLImageElement): void {
	ensureOverlay();
	if (!overlay || !overlayImg || !overlayCaption) return;

	// Show what's already decoded in the browser — zero network, instant.
	const loaded = img.currentSrc || img.src;
	overlayImg.src = loaded;
	overlayImg.alt = img.alt || "";

	// Quietly upgrade to the 2000px variant (never 4000px). Non-blocking:
	// if the fetch is slow/fails, the lightbox just keeps the loaded image.
	const hi = highResVariant(img.dataset.zoomSrc || img.src || "");
	if (hi && hi !== loaded) {
		const pre = new Image();
		pre.onload = () => {
			if (overlay && !overlay.hidden && overlayImg) overlayImg.src = hi;
		};
		pre.src = hi;
	}

	const caption = img.getAttribute("data-caption");
	overlayCaption.textContent = caption || "";
	overlayCaption.style.display = caption ? "" : "none";

	// Reveal at final (centered, contained) layout, transition off, so we
	// can measure where the image ends up.
	overlay.hidden = false;
	overlayImg.style.transition = "none";
	overlayImg.style.transform = "none";
	const finalRect = overlayImg.getBoundingClientRect();
	const srcRect = img.getBoundingClientRect();

	// FLIP: place the overlay image exactly over the clicked thumbnail, then
	// animate it to its final centered position so it "grows" out of the page.
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
