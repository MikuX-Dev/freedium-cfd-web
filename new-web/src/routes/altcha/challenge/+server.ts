import { json } from "@sveltejs/kit";
import { createChallenge } from "altcha-lib/v1";
import { env } from "$env/dynamic/private";
import type { RequestHandler } from "./$types";

function getHmacKey(): string {
	const key = env.ALTCHA_HMAC_KEY;
	if (!key) {
		console.warn(
			"[altcha] ALTCHA_HMAC_KEY is not set; using insecure dev fallback. Set ALTCHA_HMAC_KEY in production.",
		);
		return "dev-altcha-key-change-me";
	}
	return key;
}

export const GET: RequestHandler = async () => {
	const challenge = await createChallenge({
		hmacKey: getHmacKey(),
		maxNumber: 100000,
	});
	return json(challenge);
};
