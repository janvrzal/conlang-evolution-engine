<!-- Karta vpravo (detail výběru): svislý sloupec s mezerami, posouvá se sama. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let { label, rowSpan = 1, children }: { label: string; rowSpan?: number; children: Snippet } = $props();
</script>

<aside class="card" aria-label={label} style:grid-row={rowSpan > 1 ? `span ${rowSpan}` : undefined}>
	{@render children()}
</aside>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: 14px;
		min-width: 0;
		min-height: 0;
		overflow: auto;
	}
</style>
