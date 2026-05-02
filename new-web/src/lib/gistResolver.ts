/**
 * Resolve embedded gist iframes into markdown code blocks for export.
 *
 * Each iframe rendered by the backend is tagged with `data-iframe-id` and
 * served via `srcdoc` (same-origin to the parent), so we can read its
 * contentDocument and pull the gist file content out without any network
 * round-trip. Non-gist iframes (YouTube, etc.) are left as-is — the caller
 * keeps the original iframe HTML in the markdown.
 *
 * Used at download time so the saved .md file contains the actual code
 * instead of a slab of HTML the user can't read on its own.
 */

const EXT_TO_LANG: Record<string, string> = {
	py: "python",
	js: "javascript",
	mjs: "javascript",
	cjs: "javascript",
	jsx: "jsx",
	ts: "typescript",
	tsx: "tsx",
	rb: "ruby",
	sh: "bash",
	bash: "bash",
	zsh: "bash",
	fish: "fish",
	md: "markdown",
	yml: "yaml",
	yaml: "yaml",
	json: "json",
	toml: "toml",
	xml: "xml",
	html: "html",
	htm: "html",
	css: "css",
	scss: "scss",
	sass: "sass",
	cs: "csharp",
	go: "go",
	rs: "rust",
	java: "java",
	kt: "kotlin",
	swift: "swift",
	cpp: "cpp",
	cxx: "cpp",
	cc: "cpp",
	c: "c",
	h: "c",
	hpp: "cpp",
	php: "php",
	sql: "sql",
	dockerfile: "dockerfile",
	makefile: "makefile",
};

function inferLang(filename: string): string {
	const lower = filename.toLowerCase();
	if (lower === "dockerfile") return "dockerfile";
	if (lower === "makefile") return "makefile";
	const ext = lower.split(".").pop() ?? "";
	return EXT_TO_LANG[ext] ?? "";
}

function extractFilename(file: Element): string {
	const meta = file.querySelector(".gist-meta");
	if (!meta) return "gist";
	for (const link of meta.querySelectorAll("a")) {
		const text = link.textContent?.trim() ?? "";
		if (/\.[a-z0-9]+$/i.test(text)) return text;
		const href = link.getAttribute("href") ?? "";
		if (href.includes("gist.githubusercontent.com")) {
			const tail = href.split("/").pop();
			if (tail) return tail;
		}
	}
	return "gist";
}

function extractCode(file: Element): string {
	// One row per line; .blob-code-inner holds the file content. Using
	// textContent preserves the literal source while shedding GitHub's
	// syntax-highlight spans.
	const lines = Array.from(
		file.querySelectorAll<HTMLTableCellElement>("td.blob-code-inner"),
	);
	if (!lines.length) return "";
	return lines.map((td) => td.textContent ?? "").join("\n");
}

interface GistFile {
	filename: string;
	lang: string;
	code: string;
}

function extractGistFiles(iframe: HTMLIFrameElement): GistFile[] | null {
	let doc: Document | null;
	try {
		doc = iframe.contentDocument;
	} catch {
		return null;
	}
	if (!doc) return null;
	const fileEls = doc.querySelectorAll(".gist-file");
	if (!fileEls.length) return null;
	const files: GistFile[] = [];
	for (const el of fileEls) {
		const filename = extractFilename(el);
		const code = extractCode(el);
		if (!code) continue;
		files.push({ filename, lang: inferLang(filename), code });
	}
	return files.length ? files : null;
}

function escapeRegExp(s: string): string {
	return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderFileBlock(file: GistFile): string {
	return `**${file.filename}**\n\n\`\`\`${file.lang}\n${file.code}\n\`\`\``;
}

/**
 * Walk the rendered article DOM, pull gist code out of every loaded iframe,
 * and substitute matching `<iframe data-iframe-id="…">…</iframe>` blocks in
 * the source markdown with markdown code fences.
 *
 * Iframes that don't expose a gist (YouTube, Twitter, unloaded) are skipped —
 * their original HTML stays in the output.
 */
export function resolveIframesInMarkdown(
	markdown: string,
	rootSelector: string = ".prose",
): string {
	const root = document.querySelector(rootSelector);
	if (!root) return markdown;

	let out = markdown;
	const iframes = root.querySelectorAll<HTMLIFrameElement>(
		"iframe[data-iframe-id]",
	);
	for (const iframe of iframes) {
		const id = iframe.dataset.iframeId;
		if (!id) continue;
		const files = extractGistFiles(iframe);
		if (!files) continue;

		const replacement = files.map(renderFileBlock).join("\n\n");
		const pattern = new RegExp(
			`<iframe [^>]*data-iframe-id="${escapeRegExp(id)}"[^>]*></iframe>`,
			"g",
		);
		out = out.replace(pattern, replacement);
	}
	return out;
}
