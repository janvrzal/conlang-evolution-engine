<!-- Klávesa v nápovědě. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { inverse = false, children }: { inverse?: boolean; children: Snippet } = $props();
</script>

<kbd class:inverse>{@render children()}</kbd>

<style>
	kbd {
		display: inline-block;
		min-width: 20px;
		padding: 0 5px;
		border: 1px solid var(--ink-2);
		border-radius: var(--radius);
		font-size: 11px;
		font-weight: 700;
		font-family: var(--f-ui);
		text-align: center;
		line-height: 18px;
	}
	.inverse {
		border-color: var(--panel);
		color: var(--panel);
	}
</style>
