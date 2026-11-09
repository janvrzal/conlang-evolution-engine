<!-- Plovoucí panel na mapě (světlé podloží, aby text nesplýval s krajinou). -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { tight = false, children }: { tight?: boolean; children: Snippet } = $props();
</script>

<div class="floating" class:tight>{@render children()}</div>

<style>
	.floating {
		background: var(--halo);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 6px 10px;
		display: grid;
		gap: 2px;
		font-size: 13px;
	}
	.tight {
		padding: 0 4px;
		border-color: transparent;
	}
</style>
