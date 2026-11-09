<!-- Seznam odkazů či voleb (projekty, výsledky událostí). Položky jsou <ListItem>. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { label, children }: { label?: string; children: Snippet } = $props();
</script>

<ul class="list" aria-label={label}>{@render children()}</ul>

<style>
	.list {
		list-style: none;
		margin: 0;
		padding: 0;
	}
</style>
