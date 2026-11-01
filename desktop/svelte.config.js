import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	// Tauri načítá statické soubory; celá aplikace běží v prohlížeči (bez SSR).
	kit: { adapter: adapter({ fallback: 'index.html' }) }
};

export default config;
