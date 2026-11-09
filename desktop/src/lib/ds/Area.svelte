<!-- Oblast v mřížce obrazovky (sekce s popiskem); umí přes víc řádků či sloupců a vlastní posuv. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		rowSpan = 1,
		colSpan = 1,
		scroll = false,
		as = 'section',
		children
	}: { label?: string; rowSpan?: number; colSpan?: number; scroll?: boolean; as?: 'section' | 'aside' | 'div'; children: Snippet } = $props();
</script>

<svelte:element
	this={as}
	class="area"
	class:scroll
	aria-label={label}
	style:grid-row={rowSpan > 1 ? `span ${rowSpan}` : undefined}
	style:grid-column={colSpan > 1 ? `span ${colSpan}` : undefined}
>
	{@render children()}
</svelte:element>

<style>
	.area {
		min-width: 0;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.scroll {
		overflow: auto;
	}
</style>
