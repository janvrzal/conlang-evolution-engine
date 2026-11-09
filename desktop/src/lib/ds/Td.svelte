<script lang="ts">
	import type { Snippet } from 'svelte';
	let {
		num = false,
		ipa = false,
		tone,
		colspan,
		head = false,
		children
	}: {
		num?: boolean;
		ipa?: boolean;
		tone?: 'red' | 'muted';
		colspan?: number;
		/** záhlaví řádku (<th scope="row">) */
		head?: boolean;
		children?: Snippet;
	} = $props();
</script>

{#if head}
	<th scope="row" class:num {colspan}>{#if children}{@render children()}{/if}</th>
{:else}
	<td class:num class:ipa class:red={tone === 'red'} class:muted={tone === 'muted'} {colspan}>{#if children}{@render children()}{/if}</td>
{/if}

<style>
	th {
		text-align: left;
		font-weight: 400;
		font-size: 12.5px;
		color: var(--ink-2);
		padding: 5px 6px;
		border-bottom: 1px solid var(--rule);
		white-space: nowrap;
	}
	td {
		padding: 5px 6px;
		border-bottom: 1px solid var(--rule);
		vertical-align: baseline;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.ipa {
		font-family: var(--f-ipa);
		font-size: 17px;
	}
	.red {
		color: var(--red);
	}
	.muted {
		color: var(--ink-2);
		font-style: italic;
		font-size: 13px;
	}
</style>
