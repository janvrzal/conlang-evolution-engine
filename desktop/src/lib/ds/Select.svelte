<!-- Výběr ze seznamu. -->
<script lang="ts" generics="V extends string | number">
	let {
		value = $bindable(),
		options,
		label,
		id,
		onchange
	}: { value: V; options: { value: V; label: string }[]; label?: string; id?: string; onchange?: (value: V) => void } = $props();
</script>

<select {id} aria-label={label} bind:value onchange={() => onchange?.(value)}>
	{#each options as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
</select>

<style>
	select {
		background: var(--field);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 5px 8px;
		min-height: 32px;
	}
</style>
