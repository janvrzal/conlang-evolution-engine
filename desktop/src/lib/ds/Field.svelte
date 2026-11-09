<!-- Pole formuláře: popisek, volitelná hodnota vpravo, ovládání, nápověda a chyba (červený okraj). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		for: forId,
		hint,
		error,
		errorId,
		aside,
		children
	}: { label?: string; for?: string; hint?: string; error?: string | null; errorId?: string; aside?: Snippet; children?: Snippet } = $props();
</script>

<div class="field" class:err={!!error}>
	{#if label || aside}
		<div class="head">
			{#if label}{#if forId}<label for={forId}>{label}</label>{:else}<span>{label}</span>{/if}{/if}
			{#if aside}{@render aside()}{/if}
		</div>
	{/if}
	{#if children}{@render children()}{/if}
	{#if error}<p class="msg" id={errorId}>{error}</p>{/if}
	{#if hint}<p class="hint">{hint}</p>{/if}
</div>

<style>
	.field {
		display: grid;
		gap: 4px;
		padding: 10px 0;
		border-bottom: 1px solid var(--rule);
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.err {
		box-shadow: inset 3px 0 0 var(--red);
		padding-left: 10px;
	}
	.msg {
		font-size: 13px;
		color: var(--red);
	}
	.hint {
		font-size: 13px;
		color: var(--ink-2);
		font-style: italic;
	}
</style>
