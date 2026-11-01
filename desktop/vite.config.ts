import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

// Tauri v režimu vývoje čeká na pevném portu (src-tauri/tauri.conf.json → devUrl).
export default defineConfig({
	plugins: [sveltekit()],
	clearScreen: false,
	server: { port: 1420, strictPort: true },
	test: { include: ['src/**/*.test.ts'] }
});
