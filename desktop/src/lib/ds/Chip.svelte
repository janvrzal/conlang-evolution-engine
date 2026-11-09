<!-- Štítek: soused, nabídka opravy, pojem. on = vybraný, off = vypnutý. Klikací, když má onclick. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		state = 'default',
		onclick,
		onremove,
		removeLabel,
		title,
		size = 'm',
		ipa = false,
		children
	}: {
		/** s = malý štítek do tabulek (IPA inventář) */
		size?: 's' | 'm';
		/** obsah je výslovnost (písmo Charis) */
		ipa?: boolean;
		state?: 'default' | 'on' | 'off';
		onclick?: () => void;
		/** štítek jde odebrat (×) */
		onremove?: () => void;
		/** aria-label tlačítka ×, např. „Odebrat souseda Njingen“ */
		removeLabel?: string;
		title?: string;
		children: Snippet;
	} = $props();
</script>

{#if onremove}
	<span class="chip {state} {size} rm" class:ipa {title}>
		{#if onclick}<button type="button" class="in" {onclick}>{@render children()}</button>{:else}{@render children()}{/if}
		<button type="button" class="x" aria-label={removeLabel} title={removeLabel} onclick={onremove}>×</button>
	</span>
{:else}

{#if onclick}
	<button type="button" class="chip {state} {size}" class:ipa {title} aria-pressed={state === 'on' ? 'true' : undefined} {onclick}>{@render children()}</button>
{:else}
	<span class="chip {state} {size}" class:ipa {title}>{@render children()}</span>
{/if}
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
	.s {
		min-height: 24px;
		min-width: 24px;
		padding: 0 5px;
		justify-content: center;
		font-size: 14px;
	}
	.ipa {
		font-family: var(--f-ipa);
	}
	button.chip {
		cursor: pointer;
	}
	button.chip:hover {
		border-color: var(--ink-2);
	}
	.rm {
		padding-right: 2px;
	}
	.in {
		background: none;
		border: 0;
		padding: 0;
		cursor: pointer;
		font: inherit;
	}
	.x {
		background: none;
		border: 0;
		min-width: 24px;
		min-height: 24px;
		cursor: pointer;
		color: var(--ink-2);
		font-size: 15px;
		line-height: 1;
	}
	.x:hover {
		color: var(--red);
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
