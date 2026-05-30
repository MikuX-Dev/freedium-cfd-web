import apiFetch from "@/api";

interface RenderResponse {
	markdown: string;
	service: string;
	cache_status?: string;
}

interface TaskRenderResponse {
	task_id: string;
	status: string;
}

type RenderApiResponse = RenderResponse | TaskRenderResponse;

/**
 * Poll the backend's /render/poll/{taskId} endpoint until the
 * TaskIQ worker finishes rendering the article. Back off from
 * 1s → 2s → 4s up to 8s to avoid hammering Redis on long renders.
 */
async function pollTask(taskId: string, maxWaitMs = 180_000): Promise<RenderResponse> {
	const deadline = Date.now() + maxWaitMs;
	let interval = 1000;

	while (Date.now() < deadline) {
		await new Promise((r) => setTimeout(r, interval));
		if (interval < 8000) interval = Math.min(interval * 2, 8000);

		const poll = await apiFetch<{ markdown?: string; service?: string; status: string }>(
			`/render/poll/${taskId}`,
		);

		if (poll.status === "done") {
			return {
				markdown: poll.markdown!,
				service: poll.service!,
				cache_status: "miss",
			};
		}
		if (poll.status === "error") {
			throw new Error("RENDER_ERROR");
		}
		// status === "pending" — keep polling
	}
	throw new Error("RENDER_ERROR: timed out waiting for render");
}

export async function render(content: string, frontmatter = false): Promise<RenderResponse> {
	let response: RenderApiResponse | undefined;
	try {
		response = await apiFetch<RenderApiResponse>("/render", {
			method: "POST",
			body: JSON.stringify({ content, frontmatter }),
			headers: { "Content-Type": "application/json" },
		});
	} catch (err: unknown) {
		const status =
			(err as { status?: number; response?: { status?: number } })?.status ??
			(err as { response?: { status?: number } })?.response?.status;
		if (typeof status === "number") {
			throw new Error(`UPSTREAM_${status}`);
		}
		throw err;
	}

	if (!response) throw new Error("Failed to render content");

	// 202 Accepted = cold cache, TaskIQ worker is rendering.
	// Poll until the result is ready.
	if ("task_id" in response && response.status === "pending") {
		return pollTask(response.task_id);
	}

	return response as RenderResponse;
}
