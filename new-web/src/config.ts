import { env } from "$env/dynamic/public";

const API_URL = env.PUBLIC_API_URL || "http://localhost:7080/api";
const ALTCHA_ENABLED = env.PUBLIC_ALTCHA_ENABLED === "true";
// Public canonical origin, used to build Freedium links in the PDF export
// (so in-article Medium links open the Freedium version). No trailing slash.
const SITE_URL = (env.PUBLIC_SITE_URL || "https://freedium-mirror.cfd").replace(/\/$/, "");

export default {
	API_URL,
	ALTCHA_ENABLED,
	SITE_URL,
};
