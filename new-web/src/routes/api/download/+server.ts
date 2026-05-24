import { error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import config from "@/config";

export const GET: RequestHandler = async ({ url }) => {
	const articleUrl = url.searchParams.get("url");
	if (!articleUrl) {
		throw error(400, "Missing url parameter");
	}

	const backendUrl = `${config.API_URL}/articles/download?${new URLSearchParams({ url: articleUrl })}`;

	const res = await fetch(backendUrl);
	if (!res.ok) {
		throw error(res.status, `Backend returned ${res.status}`);
	}

	const body = await res.text();
	const contentDisposition = res.headers.get("content-disposition") || `attachment; filename="article.md"`;

	return new Response(body, {
		status: 200,
		headers: {
			"content-type": "text/markdown; charset=utf-8",
			"content-disposition": contentDisposition,
		},
	});
};
