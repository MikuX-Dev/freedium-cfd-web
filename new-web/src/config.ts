import { env } from "$env/dynamic/public";

const API_URL = env.PUBLIC_API_URL || "http://localhost:7080/api";
const ALTCHA_ENABLED = env.PUBLIC_ALTCHA_ENABLED === "true";

export default {
	API_URL,
	ALTCHA_ENABLED,
};
