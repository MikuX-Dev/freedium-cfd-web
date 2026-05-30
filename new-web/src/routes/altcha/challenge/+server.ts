import { error, json } from "@sveltejs/kit";
import { createChallenge } from "altcha-lib/v1";
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

export const GET: RequestHandler = async () => {
	const challenge = await createChallenge({
		hmacKey: getHmacKey(),
		maxNumber: 100000,
		expires: new Date(Date.now() + 5 * 60 * 1000),
	});
	return json(challenge);
};
