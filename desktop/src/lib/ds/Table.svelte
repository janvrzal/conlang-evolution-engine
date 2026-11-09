<!-- Tabulka. Hlavička z `head`, řádky jako <Tr><Td>…</Td></Tr>. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let {
		head,
		caption,
		scroll = false,
		children
	}: { head?: { label: string; num?: boolean }[]; caption?: string; /** široká tabulka se posouvá vodorovně */ scroll?: boolean; children: Snippet } = $props();
</script>

<div class="wrap" class:scroll>
<table class="t">
	{#if caption}<caption>{caption}</caption>{/if}
	{#if head}
		<thead><tr>{#each head as h, i (i)}<th class:num={h.num}>{h.label}</th>{/each}</tr></thead>
	{/if}
	<tbody>{@render children()}</tbody>
</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
	}
	.t {
		border-collapse: collapse;
		width: 100%;
		font-size: 14px;
	}
	caption {
		text-align: left;
		font-size: 12px;
		color: var(--ink-2);
		padding-bottom: 4px;
	}
	th {
		text-align: left;
		font-weight: 500;
		color: var(--ink-2);
		font-size: 12px;
		padding: 5px 6px;
		border-bottom: 1px solid var(--ink);
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
</style>
