import { ofetch } from "ofetch";
import config from "./config";

// Backend renders can take 30-90s on a cold cache for big articles
// (long Medium pages with many images go through the WARP proxy chain,
// each Medium GraphQL hop adds 200-500ms). Node's undici defaults bite
// at 30s — bump the SSR-side fetch timeout to 120s so the user gets
// the rendered article instead of a 500 + cached "Failed to render".
const apiFetch = ofetch.create({
	baseURL: config.API_URL,
	timeout: 120_000,
});

export default apiFetch;
