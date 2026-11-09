<!-- Legenda mapy: plocha, čára, obrys, čtvereček města. Pod položky lze dát poznámku (children). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	export interface LegendItem {
		label: string;
		color?: string;
		/** isogloss = červená čára (za ní se slovo říká jinak) */
		kind?: 'fill' | 'line' | 'dashed' | 'outline' | 'square' | 'hatch' | 'isogloss';
	}
	let { items, children }: { items: LegendItem[]; children?: Snippet } = $props();
</script>

<div class="legend">
	{#each items as item, i (i)}
		<div class="item"><i class={item.kind ?? 'fill'} style:--c={item.color ?? 'var(--ink)'} aria-hidden="true"></i>{item.label}</div>
	{/each}
	{#if children}<div class="note">{@render children()}</div>{/if}
</div>

<style>
	.legend {
		display: grid;
		gap: 4px;
		font-size: 12.5px;
	}
	.item {
		display: flex;
		align-items: center;
	}
	i {
		display: inline-block;
		width: 18px;
		height: 10px;
		margin-right: 6px;
		border-radius: 1px;
		flex: none;
	}
	.fill {
		background: var(--c);
	}
	.line {
		height: 2px;
		background: var(--c);
	}
	.isogloss {
		height: 2px;
		background: var(--red);
	}
	.dashed {
		height: 0;
		border-top: 2px dashed var(--c);
	}
	.outline {
		border: 2px solid var(--c);
	}
	.square {
		width: 8px;
		height: 8px;
		border: 2px solid var(--c);
		margin: 0 11px 0 5px;
	}
	.hatch {
		background: repeating-linear-gradient(-45deg, var(--c) 0 1px, transparent 1px 5px);
		border: 1px solid var(--c);
	}
	.note {
		font-size: 12px;
		color: var(--ink-2);
		font-style: italic;
	}
</style>
