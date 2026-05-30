/// <reference types="unplugin-icons/types/svelte" />

// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

// Type declaration for unplugin-icons raw imports
declare module '~icons/*?raw' {
	const src: string;
	export default src;
}

// The ALTCHA web component (<altcha-widget>) is a custom element with no
// built-in Svelte/JSX typing. Declare its attributes so svelte-check passes.
declare namespace svelteHTML {
	interface IntrinsicElements {
		'altcha-widget': {
			challengeurl?: string;
			[key: string]: unknown;
		};
	}
}

export {};
