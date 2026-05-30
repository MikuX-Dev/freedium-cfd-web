import { render } from "@/services";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import rehypeStringify from "rehype-stringify";
import { createHighlighter, type HighlighterGeneric, type BundledLanguage, type BundledTheme } from "shiki";
import { visit } from "unist-util-visit";
import { toHtml } from "hast-util-to-html";
import { h, s } from "hastscript";
import type { Element, Root } from "hast";
import { getIconData, iconToSVG } from "@iconify/utils";
import heroiconsData from "@iconify/json/json/heroicons.json";
import rehypeExternalLinks from "rehype-external-links";
import rehypeSlug from "rehype-slug";
import FrontMatter from "front-matter";

// Helper to get icon as HAST SVG node
function getIconHast(iconName: string, customAttrs: Record<string, string> = {}): Element | null {
	const iconData = getIconData(heroiconsData, iconName);
	if (!iconData) {
		console.warn(`Icon "${iconName}" not found in heroicons`);
		return null;
	}
	const renderData = iconToSVG(iconData, { height: "1em", width: "1em" });
	const attrs = {
		...renderData.attributes,
		...customAttrs,
		xmlns: "http://www.w3.org/2000/svg",
	};

	const svgElement = s("svg", attrs) as Element;
	// Inject raw SVG body content
	(svgElement.children as unknown[]).push({ type: "raw", value: renderData.body });
	return svgElement;
}

// Create external link icon
const externalLinkIcon = getIconHast("arrow-top-right-on-square", {
	class: "inline-block ml-0.5 size-3 align-baseline relative -top-px",
	stroke: "currentColor",
	fill: "none",
	"stroke-width": "2",
	"aria-hidden": "true",
});

const HIGHLIGHT_CONFIG = {
	themes: ["github-light", "github-dark"],
	langs: ["javascript", "typescript", "nginx", "bash", "ruby", "python"],
};

const CODE_ATTRIBUTES: Record<string, string> = {
	contenteditable: "true",
	"aria-label": "code",
	"aria-readonly": "true",
	inputmode: "none",
	tabindex: "0",
	"aria-multiline": "true",
	"aria-haspopup": "false",
	"data-gramm": "false",
	"data-gramm_editor": "false",
	"data-enable-grammarly": "false",
	spellcheck: "false",
	autocorrect: "off",
	autocapitalize: "none",
	autocomplete: "off",
	"data-ms-editor": "false",
};

let highlighterInstance: HighlighterGeneric<BundledLanguage, BundledTheme> | null = null;

async function getHighlighter(): Promise<HighlighterGeneric<BundledLanguage, BundledTheme>> {
	if (!highlighterInstance) {
		highlighterInstance = await createHighlighter(HIGHLIGHT_CONFIG);
		await highlighterInstance.loadLanguage("javascript", "typescript", "nginx", "bash", "ruby", "python");
	}
	return highlighterInstance;
}

/** codeToHtml wrapper that falls back to "text" for unsupported languages.
 * Medium articles can contain code blocks in any language — kotlin, java,
 * markdown, css, etc. — but we only pre-load a handful. This keeps the
 * render pipeline from crashing on unknown languages. */
function safeCodeToHtml(
	highlighter: HighlighterGeneric<BundledLanguage, BundledTheme>,
	code: string,
	lang: string,
	options: Record<string, unknown>,
): string {
	try {
		return highlighter.codeToHtml(code, { ...options, lang } as Parameters<typeof highlighter.codeToHtml>[1]);
	} catch (e) {
		if (e instanceof Error && (e.name === "ShikiError" || e.message?.includes("Language"))) {
			return highlighter.codeToHtml(code, { ...options, lang: "text" } as Parameters<typeof highlighter.codeToHtml>[1]);
		}
		throw e;
	}
}

function createCodeCopyButton(code: string, toggleMs: number = 3000): string {
	const lineCount = code.split("\n").length;
	const positionClass = lineCount <= 3 ? "top-1/2 -translate-y-1/2" : "top-3";

	const clipboardIcon = getIconHast("clipboard-document", {
		class: "size-5",
		stroke: "currentColor",
		fill: "none",
		"stroke-width": "1.5"
	});

	const clipboardCheckIcon = getIconHast("clipboard-document-check-solid", {
		class: "size-5",
		fill: "currentColor"
	});

	const button = h(
		"button",
		{
			"data-code": code,
			"data-toggle-ms": toggleMs,
			class: `code-copy-btn absolute right-3 ${positionClass} size-8 p-1.5 flex items-center justify-center bg-black/50 text-white rounded-md transition-colors duration-200 cursor-pointer hover:bg-black/70`,
		},
		[
			h("span", { class: "ready block" }, clipboardIcon ? [clipboardIcon] : []),
			h("span", { class: "success hidden" }, clipboardCheckIcon ? [clipboardCheckIcon] : []),
		],
	);

	return toHtml(button, { allowDangerousHtml: true });
}

// Rehype plugin for syntax highlighting
function rehypeHighlight(opts: { mode: RenderMode } = { mode: "web" }) {
	return async (tree: Root) => {
		const highlighter = await getHighlighter();
		const nodesToReplace: Array<{ node: any; parent: any; index: number; replacement: any }> = [];

		visit(tree, 'element', (node: any, index: number | null | undefined, parent: any) => {
			if (node.tagName === 'pre') {
				const codeNode = node.children?.[0];
				if (codeNode && codeNode.tagName === 'code') {
					const className = codeNode.properties?.className;
					const lang = className?.[0]?.replace('language-', '') || 'text';
					// Remove trailing newline that remark-parse adds to all code blocks
					const originalText = codeNode.children?.[0]?.value || '';
					const codeText = originalText.replace(/\n$/, '');


					// Check for decorations in code fence meta (e.g., ```lang decorations="[...]")
					const meta = codeNode.data?.meta || '';
					let decorations: Array<{ start: number; end: number; properties: any }> = [];

					// Match decorations with escaped quotes - need to find the closing quote
					const decorationsMatch = meta.match(/decorations="(.+)"$/);
					if (decorationsMatch) {
						try {
							// Unescape the JSON
							const jsonStr = decorationsMatch[1].replace(/\\"/g, '"');
							const decoData = JSON.parse(jsonStr);
							decorations = decoData.map((d: any) => ({
								// Clamp positions to code length to handle Medium's invalid markup positions
								start: Math.min(d.start, codeText.length),
								end: Math.min(d.end, codeText.length),
								properties: { class: d.type === 'strong' ? 'font-bold' : 'italic' }
							}))
							// Filter out invalid decorations where start >= end
							.filter((d: any) => d.start < d.end);
						} catch (e) {
							console.error('Failed to parse decorations:', e);
						}
					}


					// Generate highlighted HTML with decorations
					const lightHtml = safeCodeToHtml(highlighter, codeText, lang, {

						theme: "github-light",
						decorations,
						transformers: [
							{
								code(transformNode) {
									transformNode.properties = { ...transformNode.properties, ...CODE_ATTRIBUTES };
									return transformNode;
								},
							},
						],
					});

					let wrappedHtml: string;
					if (opts.mode === "print") {
						// Print: single theme, no dark variant, no copy button.
						wrappedHtml = lightHtml;
					} else {
						// Web: dual theme + copy button (existing behavior).
						const darkHtml = safeCodeToHtml(highlighter, codeText, lang, {
	
							theme: "github-dark",
							decorations,
							transformers: [
								{
									code(transformNode) {
										transformNode.properties = { ...transformNode.properties, ...CODE_ATTRIBUTES };
										return transformNode;
									},
								},
							],
						});

						const buttonHtml = createCodeCopyButton(codeText, 1200);

						// Create replacement HTML
						wrappedHtml = `
						<div class="relative">
							${buttonHtml}
							<div class="dark:hidden">${lightHtml}</div>
							<div class="hidden dark:block">${darkHtml}</div>
						</div>
					`;
					}

					// Create a raw HTML node
					const replacement = {
						type: 'raw',
						value: wrappedHtml
					};

					if (parent && typeof index === 'number') {
						nodesToReplace.push({ node, parent, index, replacement });
					}
				}
			}
		});

		// Replace nodes
		for (const { parent, index, replacement } of nodesToReplace) {
			parent.children[index] = replacement;
		}
	};
}

const YOUTUBE_PATTERNS = [
	/youtube\.com\/embed\/([A-Za-z0-9_-]{6,15})/,
	/youtube\.com\/watch\?v=([A-Za-z0-9_-]{6,15})/,
	/youtu\.be\/([A-Za-z0-9_-]{6,15})/,
];

function extractYouTubeId(src: string): string | null {
	for (const re of YOUTUBE_PATTERNS) {
		const m = src.match(re);
		if (m) return m[1];
	}
	return null;
}

function escapeHtml(s: string): string {
	return s
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

function buildIframeFallbackLink(src: string): string {
	try {
		const u = new URL(src);
		if (u.protocol !== "http:" && u.protocol !== "https:") {
			return `<a href="#">[Embed]</a>`;
		}
		return `<a href="${escapeHtml(src)}">[Embed: ${escapeHtml(u.hostname)}]</a>`;
	} catch {
		return `<a href="#">[Embed]</a>`;
	}
}

function transformIframeHtml(iframeHtml: string): string {
	const srcMatch = iframeHtml.match(/\bsrc\s*=\s*["']([^"']+)["']/i);
	if (!srcMatch) return iframeHtml;
	const src = srcMatch[1];

	const ytId = extractYouTubeId(src);
	if (ytId) {
		return (
			`<a class="yt-link" href="https://www.youtube.com/watch?v=${ytId}">` +
			`<img class="yt-thumb" src="https://img.youtube.com/vi/${ytId}/maxresdefault.jpg" alt="YouTube video"/>` +
			`<span class="yt-play">▶</span>` +
			`</a>`
		);
	}

	return buildIframeFallbackLink(src);
}

function rehypeIframeToThumbnail() {
	return (tree: Root) => {
		// Iframes appear as either:
		// 1. element nodes (when remark parses them as inline HTML inside paragraphs and rehype-raw runs), or
		// 2. raw nodes (when remark-rehype { allowDangerousHtml: true } passes block-level HTML through).
		// We handle both.

		visit(tree, "element", (node: any, index: number | null | undefined, parent: any) => {
			if (node.tagName !== "iframe") return;
			if (!parent || typeof index !== "number") return;

			const src = node.properties?.src;
			if (typeof src !== "string") return;

			const ytId = extractYouTubeId(src);
			const replacement = ytId
				? {
						type: "raw" as const,
						value:
							`<a class="yt-link" href="https://www.youtube.com/watch?v=${ytId}">` +
							`<img class="yt-thumb" src="https://img.youtube.com/vi/${ytId}/maxresdefault.jpg" alt="YouTube video"/>` +
							`<span class="yt-play">▶</span>` +
							`</a>`,
					}
				: {
						type: "raw" as const,
						value: buildIframeFallbackLink(src),
					};

			parent.children[index] = replacement;
		});

		// Transform raw HTML nodes whose value contains an <iframe>.
		visit(tree, "raw" as any, (node: any) => {
			if (typeof node.value !== "string") return;
			if (!/<iframe\b/i.test(node.value)) return;
			// Lazy [\s\S]*? matches iframes with body content (e.g., fallback text)
			// without gobbling across two adjacent iframes.
			node.value = node.value.replace(/<iframe\b[^>]*>[\s\S]*?<\/iframe>/gi, (match: string) =>
				transformIframeHtml(match),
			);
			// Also handle self-closing or void-style iframes just in case.
			node.value = node.value.replace(/<iframe\b[^>]*\/>/gi, (match: string) =>
				transformIframeHtml(match),
			);
		});
	};
}

export type RenderMode = "web" | "print";

export interface ArticleMetadata {
	title: string;
	subtitle?: string;
	author: { name: string; avatar: string; role: string };
	date: string;
	postImage: string | null;
	postImageZoom: string | null;
	postImageCaption?: string;
	url: string | null;
	tableOfContents: Array<{ id: string; title: string }>;
}

export interface RenderResult {
	html: string;
	markdown: string;
	article: ArticleMetadata | null;
	cacheStatus: string;
}

export async function renderArticle(
	slug: string,
	options: { mode?: RenderMode } = {},
): Promise<RenderResult> {
	const mode = options.mode ?? "web";

	const renderResult = await render(slug, true);
	if (!renderResult) throw new Error("ARTICLE_NOT_FOUND");

	let article: ArticleMetadata | null = null;
	let markdownContent = renderResult.markdown;

	try {
		const parsed = FrontMatter(renderResult.markdown);
		const metadata = parsed.attributes as Record<string, any>;
		markdownContent = parsed.body;

		// Use table_of_contents from frontmatter
		let tableOfContents: Array<{ id: string; title: string }> = [];

		if (metadata.table_of_contents && Array.isArray(metadata.table_of_contents)) {
			tableOfContents = metadata.table_of_contents;
		}

		// Extract preview image - handle both responsive object and simple string formats
		let postImage: string | null = null;
		let postImageZoom: string | null = null;
		let postImageCaption: string | null = null;
		if (metadata.preview_image) {
			if (typeof metadata.preview_image === "string") {
				// Simple string format (backward compatibility or base64 data URI)
				postImage = metadata.preview_image;
			} else if (typeof metadata.preview_image === "object" && metadata.preview_image.medium) {
				// Responsive object format - use medium for display, zoom for HD
				postImage = metadata.preview_image.medium;
				postImageZoom = metadata.preview_image.zoom || null;
				postImageCaption = metadata.preview_image.caption || null;
			}
		}

		// Extract author information - handle both old string format and new object format
		let author = {
			name: "Unknown",
			avatar: `https://ui-avatars.com/api/?name=Unknown&background=random`,
			role: "Author",
		};

		if (metadata.author) {
			if (typeof metadata.author === "string") {
				// Old format: just author name string
				author.name = metadata.author;
				author.avatar = `https://ui-avatars.com/api/?name=${encodeURIComponent(metadata.author)}&background=random`;
			} else if (typeof metadata.author === "object" && metadata.author.name) {
				// New format: author object with name and avatar
				author.name = metadata.author.name;
				if (metadata.author.avatar) {
					author.avatar = metadata.author.avatar;
				} else {
					author.avatar = `https://ui-avatars.com/api/?name=${encodeURIComponent(metadata.author.name)}&background=random`;
				}
			}
		}

		// Add reading time as role if available
		if (metadata.reading_time) {
			author.role = `${metadata.reading_time} min read`;
		}

		article = {
			title: metadata.title || "Untitled",
			subtitle: metadata.subtitle || undefined,
			author,
			date: new Date().toISOString(),
			postImage,
			postImageZoom,
			postImageCaption: postImageCaption || undefined,
			url: metadata.url || null,
			tableOfContents,
		};
	} catch (error) {
		console.warn("Failed to parse frontmatter:", error);
	}

	const baseProcessor = unified()
		.use(remarkParse)
		.use(remarkRehype, { allowDangerousHtml: true })
		.use(rehypeSlug)
		.use(rehypeExternalLinks, {
			target: "_blank",
			rel: ["nofollow"],
			content: mode === "print" ? undefined : externalLinkIcon,
		});

	const withIframeTransform =
		mode === "print" ? baseProcessor.use(rehypeIframeToThumbnail) : baseProcessor;

	const processor = withIframeTransform
		.use(rehypeHighlight, { mode })
		.use(rehypeStringify, { allowDangerousHtml: true });

	const result = await processor.process(markdownContent);

	// Render the cover-image caption through the SAME pipeline so markdown spans
	// (links, emphasis, code) become HTML — body figcaptions get rendered because
	// medium-parser drops them into the body markdown stream; this caption lives
	// in YAML frontmatter and would otherwise reach the client as raw markdown.
	if (article && article.postImageCaption) {
		const captionHtml = String(await processor.process(article.postImageCaption));
		// Strip the wrapping <p>…</p> remark-rehype adds; <figcaption> is an
		// inline-content context, so a block paragraph is wrong here.
		article.postImageCaption = captionHtml
			.trim()
			.replace(/^<p>([\s\S]*)<\/p>$/, "$1")
			.trim();
	}

	return {
		html: String(result),
		markdown: markdownContent,
		article,
		cacheStatus: renderResult.cache_status ?? "miss",
	};
}
