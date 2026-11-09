<!-- Pata zadání: souhrn, ověření, Zpět/Znovu a Spustit vpravo (vlož <Spacer/>). -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { label, children }: { label?: string; children: Snippet } = $props();
</script>

<footer class="foot" aria-label={label}>{@render children()}</footer>

<style>
	.foot {
		position: relative;
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
		padding: 8px 16px 10px;
		border-top: 1px solid var(--rule);
		font-size: 13px;
		color: var(--ink-2);
	}
</style>
