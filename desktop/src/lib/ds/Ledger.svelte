<!-- Seznam „pojem – hodnota“ (údaje kraje, události, jazyka). Řádky jsou <LedgerRow>. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { termWidth = 120, children }: { termWidth?: number; children: Snippet } = $props();
</script>

<dl class="ledger" style:--term="{termWidth}px">{@render children()}</dl>

<style>
	.ledger {
		display: grid;
		margin: 0;
	}
</style>
