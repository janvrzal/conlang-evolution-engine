<!-- Řádek parametru: název a kód vlevo, ovládání vpravo, výchozí hodnota pod ním.
     Změněný proti výchozí hodnotě má červený okraj (ruka autora). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		code,
		changed = false,
		note,
		control,
		children
	}: {
		label: string;
		/** technické jméno parametru */
		code?: string;
		changed?: boolean;
		/** výchozí hodnota, popis */
		note?: string;
		/** ovládání vpravo (Range, TextInput, Segmented) */
		control: Snippet;
		/** další obsah pod řádkem (celý popis, Vrátit) */
		children?: Snippet;
	} = $props();
</script>

<div class="row" class:changed>
	<div class="name">
		<span>{label}</span>
		{#if code}<code>{code}</code>{/if}
	</div>
	<div class="control">{@render control()}</div>
	{#if note}<p class="note">{note}</p>{/if}
	{#if children}<div class="more">{@render children()}</div>{/if}
</div>

<style>
	.row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(140px, 220px);
		gap: 2px 12px;
		align-items: center;
		padding: 8px 0 8px 10px;
		border-bottom: 1px solid var(--rule);
	}
	.changed {
		box-shadow: inset 3px 0 0 var(--red);
	}
	.name {
		display: grid;
		gap: 1px;
		min-width: 0;
	}
	code {
		font-size: 11.5px;
		color: var(--ink-2);
	}
	.note {
		grid-column: 1 / -1;
		font-size: 12.5px;
		color: var(--ink-2);
		font-style: italic;
	}
	.changed .note {
		color: var(--red);
	}
	.more {
		grid-column: 1 / -1;
	}
</style>
