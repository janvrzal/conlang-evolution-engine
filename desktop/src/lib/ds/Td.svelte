<script lang="ts">
	import type { Snippet } from 'svelte';
	let {
		num = false,
		ipa = false,
		tone,
		colspan,
		children
	}: { num?: boolean; ipa?: boolean; tone?: 'red' | 'muted'; colspan?: number; children?: Snippet } = $props();
</script>

<td class:num class:ipa class:red={tone === 'red'} class:muted={tone === 'muted'} {colspan}>{#if children}{@render children()}{/if}</td>

<style>
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
