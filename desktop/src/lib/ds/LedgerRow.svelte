<script lang="ts">
	import type { Snippet } from 'svelte';
	let { term, children }: { term: string; children: Snippet } = $props();
</script>

<div class="row">
	<dt>{term}</dt>
	<dd>{@render children()}</dd>
</div>

<style>
	.row {
		display: grid;
		grid-template-columns: var(--term, 120px) minmax(0, 1fr);
		gap: 10px;
		padding: 7px 0;
		border-bottom: 1px solid var(--rule);
		font-size: 14px;
	}
	dt {
		color: var(--ink-2);
	}
	dd {
		margin: 0;
	}
</style>
