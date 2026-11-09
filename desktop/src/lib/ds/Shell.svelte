<!-- Kostra aplikace: lišta, volitelný pruh hlášení, obsah a pata (časová osa nebo pata zadání). -->
<script lang="ts">
	import './tokens.css';
	import '@fontsource/piazzolla/400.css';
	import '@fontsource/piazzolla/400-italic.css';
	import '@fontsource/piazzolla/500.css';
	import '@fontsource/piazzolla/700.css';
	import type { Snippet } from 'svelte';

	let { bar, banner, footer, children }: { bar: Snippet; banner?: Snippet; footer?: Snippet; children: Snippet } = $props();
</script>

<div class="shell">
	{@render bar()}
	{#if banner}{@render banner()}{/if}
	<main class="main">{@render children()}</main>
	{#if footer}{@render footer()}{/if}
</div>

<style>
	.shell {
		height: 100vh;
		display: grid;
		grid-template-rows: auto auto minmax(0, 1fr) auto;
		background: var(--panel);
	}
	.main {
		min-height: 0;
		overflow: auto;
		display: flex;
		flex-direction: column;
	}
</style>
