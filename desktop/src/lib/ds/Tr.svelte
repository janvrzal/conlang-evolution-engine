<script lang="ts">
	import type { Snippet } from 'svelte';
	let { selected = false, onclick, children }: { selected?: boolean; onclick?: () => void; children: Snippet } = $props();
	function key(event: KeyboardEvent) {
		if (onclick && (event.key === 'Enter' || event.key === ' ')) {
			event.preventDefault();
			onclick();
		}
	}
</script>

<tr class:selected class:click={!!onclick} {onclick} onkeydown={key} tabindex={onclick ? 0 : undefined} aria-selected={onclick ? selected : undefined}>{@render children()}</tr>

<style>
	.selected {
		background: var(--sel);
		box-shadow: inset 2px 0 0 var(--ink);
	}
	.click {
		cursor: pointer;
	}
	.click:hover {
		background: var(--field);
	}
</style>
