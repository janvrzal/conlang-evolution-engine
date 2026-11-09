<!-- Rozbalovací blok: tlačítko se šipkou a obsah, který se ukáže po kliknutí (drobné změny století, podrobnosti). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		summary,
		children
	}: {
		open?: boolean;
		/** text nebo obsah tlačítka (vždy viditelný) */
		summary: Snippet;
		children: Snippet;
	} = $props();
	const uid = $props.id();
</script>

<div class="disclosure">
	<button type="button" class="toggle" aria-expanded={open} aria-controls="{uid}-body" onclick={() => (open = !open)}>
		<span class="arrow" class:open aria-hidden="true">▸</span>
		<span class="summary">{@render summary()}</span>
	</button>
	{#if open}<div class="body" id="{uid}-body">{@render children()}</div>{/if}
</div>

<style>
	.disclosure {
		display: grid;
		gap: 4px;
	}
	.toggle {
		display: flex;
		align-items: baseline;
		gap: 6px;
		min-height: 28px;
		padding: 2px 4px;
		background: none;
		border: 0;
		border-radius: var(--radius);
		cursor: pointer;
		text-align: left;
		color: inherit;
		font: inherit;
	}
	.toggle:hover {
		background: var(--field);
	}
	.arrow {
		font-size: 11px;
		color: var(--ink-2);
		transition: transform 0.12s;
	}
	.arrow.open {
		transform: rotate(90deg);
	}
	.summary {
		min-width: 0;
	}
	.body {
		padding-left: 18px;
	}
</style>
