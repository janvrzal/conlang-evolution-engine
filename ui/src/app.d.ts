// See https://svelte.dev/docs/kit/types#app.d.ts
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

interface ImportMetaEnv {
	/** Adresa CEE API; zapisuje ji `cee ui` do `ui/.env.local`. */
	readonly VITE_CEE_API_URL?: string;
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}

export {};
