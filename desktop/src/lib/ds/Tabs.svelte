<!-- Karty uvnitř panelu. Šipky vlevo/vpravo přepínají. -->
<script lang="ts" generics="V extends string">
	let {
		tabs,
		value = $bindable(),
		label,
		onchange
	}: { tabs: { id: V; label: string }[]; value: V; label: string; onchange?: (value: V) => void } = $props();

	function pick(id: V) {
		value = id;
		onchange?.(id);
	}
	function key(event: KeyboardEvent) {
		const i = tabs.findIndex((t) => t.id === value);
		if (event.key === 'ArrowRight') pick(tabs[(i + 1) % tabs.length].id);
		else if (event.key === 'ArrowLeft') pick(tabs[(i - 1 + tabs.length) % tabs.length].id);
	}
</script>

<div class="tabs" role="tablist" aria-label={label} tabindex="-1" onkeydown={key}>
	{#each tabs as tab (tab.id)}
		<button type="button" role="tab" aria-selected={tab.id === value} tabindex={tab.id === value ? 0 : -1} onclick={() => pick(tab.id)}>{tab.label}</button>
	{/each}
</div>

<style>
	.tabs {
		display: flex;
		gap: 18px;
		flex-wrap: wrap;
		border-bottom: 1px solid var(--rule);
	}
	button {
		background: none;
		border: 0;
		min-height: 34px;
		padding: 4px 0 6px;
		cursor: pointer;
		font-size: 16px;
		color: var(--ink-2);
		border-bottom: 2.5px solid transparent;
		margin-bottom: -1px;
	}
	button[aria-selected='true'] {
		color: var(--ink);
		font-weight: 500;
		border-bottom-color: var(--ink);
	}
</style>
