<!-- Tlačítko, které otevře výběr souboru a předá vybraný soubor. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon from './Icon.svelte';

	let { accept, onfile, label, children }: { accept?: string; onfile: (file: File) => void; /** jen ikona: popisek pro čtečku a nápovědu */ label?: string; children?: Snippet } = $props();
	let input: HTMLInputElement;
	function change() {
		const file = input.files?.[0];
		if (file) onfile(file);
		input.value = '';
	}
</script>

<button type="button" class="btn" class:icon={!children} aria-label={label} title={label} onclick={() => input.click()}><Icon name="open" />{#if children}{@render children()}{/if}</button>
<input bind:this={input} type="file" {accept} hidden onchange={change} />

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 32px;
		background: var(--field);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 4px 12px;
		cursor: pointer;
		font-size: 14px;
	}
	.btn:hover {
		border-color: var(--ink-2);
	}
	.icon {
		padding: 4px 8px;
	}
</style>
