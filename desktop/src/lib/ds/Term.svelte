<!-- Odborný výraz s vysvětlením na najetí (title) – podtržený tečkami. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { explain, children }: { explain: string; children: Snippet } = $props();
</script>

<abbr title={explain}>{@render children()}</abbr>

<style>
	abbr {
		text-decoration: underline dotted var(--ink-2);
		text-underline-offset: 3px;
		cursor: help;
	}
</style>
