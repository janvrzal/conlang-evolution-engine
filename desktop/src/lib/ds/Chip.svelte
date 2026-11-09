<!-- Štítek: soused, nabídka opravy, pojem. on = vybraný, off = vypnutý. Klikací, když má onclick. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let { state = 'default', onclick, title, children }: { state?: 'default' | 'on' | 'off'; onclick?: () => void; title?: string; children: Snippet } = $props();
</script>

{#if onclick}
	<button type="button" class="chip {state}" {title} aria-pressed={state === 'on' ? 'true' : undefined} {onclick}>{@render children()}</button>
{:else}
	<span class="chip {state}" {title}>{@render children()}</span>
{/if}

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		min-height: 28px;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 2px 8px;
		font-size: 13px;
		background: var(--field);
	}
	button.chip {
		cursor: pointer;
	}
	button.chip:hover {
		border-color: var(--ink-2);
	}
	.on {
		border-color: var(--ink);
		box-shadow: inset 0 -2px 0 var(--ink);
	}
	.off {
		color: var(--ink-3);
		background: none;
		border-style: dashed;
	}
</style>
