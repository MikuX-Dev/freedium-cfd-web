import { AsyncLocalStorage } from "node:async_hooks";

/** Per-request User-Agent, set by hooks.server.ts for the
 *  duration of every SSR request. apiFetch reads it to forward
 *  the real browser/bot UA to the backend as X-Client-UA. */
export const clientUaStore = new AsyncLocalStorage<string>();

/** The original User-Agent for the current request context,
 *  or empty when called outside SSR (e.g. client-side hydration). */
export function getClientUa(): string {
	return clientUaStore.getStore() ?? "";
}
