<!-- Prázdný stav obrazovky: dýchající značka, nadpis, vysvětlení a volitelné akce (co udělat dál). -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import BrandMark from './BrandMark.svelte';

	let { title, text, actions }: { title: string; text: string; actions?: Snippet } = $props();
</script>

<section class="empty">
	<span class="mk"><BrandMark mode="idle" size={72} /></span>
	<h1>{title}</h1>
	<p>{text}</p>
	{#if actions}<div class="actions">{@render actions()}</div>{/if}
</section>

<style>
	.empty {
		display: grid;
		justify-items: start;
		align-content: start;
		gap: 10px;
		max-width: 560px;
		padding: 48px 32px;
	}
	.mk {
		color: var(--ink);
		margin-left: -8px;
		margin-bottom: 6px;
	}
	h1 {
		margin: 0;
		font-size: 26px;
		font-weight: 500;
	}
	p {
		margin: 0;
		font-style: italic;
		color: var(--ink-2);
		line-height: 1.5;
	}
	.actions {
		display: flex;
		gap: 8px;
		margin-top: 8px;
	}
</style>
