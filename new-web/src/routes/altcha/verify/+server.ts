import { error, json } from "@sveltejs/kit";
import { verifySolution } from "altcha-lib/v1";
import { env } from "$env/dynamic/private";
import type { RequestHandler } from "./$types";

function getHmacKey(): string {
	const key = env.ALTCHA_HMAC_KEY;
	if (key) return key;
	if (import.meta.env.DEV) {
		console.warn(
			"[altcha] ALTCHA_HMAC_KEY is not set; using insecure dev fallback (DEV only).",
		);
		return "dev-altcha-key-change-me";
	}
	throw error(500, "ALTCHA_HMAC_KEY not configured");
}

export const POST: RequestHandler = async ({ request }) => {
	const { payload } = await request.json().catch(() => ({ payload: null }));
	if (!payload) return json({ ok: false }, { status: 400 });
	const ok = await verifySolution(payload, getHmacKey());
	return json({ ok });
};
