<!-- Zaškrtávátko s popiskem; volitelně značka a počet vpravo (filtry kroniky). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		checked = $bindable(),
		meta,
		onchange,
		children
	}: { checked: boolean; meta?: string; onchange?: (checked: boolean) => void; children: Snippet } = $props();
</script>

<label class="check">
	<input type="checkbox" bind:checked onchange={() => onchange?.(checked)} />
	<span class="text">{@render children()}</span>
	{#if meta}<small>{meta}</small>{/if}
</label>

<style>
	.check {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 32px;
		padding: 2px 4px;
		border-radius: var(--radius);
		cursor: pointer;
	}
	.check:hover {
		background: var(--field);
	}
	.text {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	small {
		margin-left: auto;
		font-size: 12px;
		color: var(--ink-2);
		font-style: italic;
	}
	input {
		accent-color: var(--ink);
		width: 16px;
		height: 16px;
	}
</style>
