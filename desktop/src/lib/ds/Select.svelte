<!-- Výběr ze seznamu. -->
<script lang="ts" generics="V extends string | number">
	let {
		value = $bindable(),
		options,
		label,
		id,
		onchange
	}: {
		value: V;
		/** `group` seskupí volby pod nadpis (optgroup) v pořadí prvního výskytu */
		options: { value: V; label: string; group?: string }[];
		label?: string;
		id?: string;
		onchange?: (value: V) => void;
	} = $props();
	const groups = $derived.by(() => {
		const out: { name: string | undefined; items: typeof options }[] = [];
		for (const o of options) {
			const last = out.at(-1);
			if (last && last.name === o.group) last.items.push(o);
			else out.push({ name: o.group, items: [o] });
		}
		return out;
	});
</script>

<select {id} aria-label={label} bind:value onchange={() => onchange?.(value)}>
	{#each groups as g, i (i)}
		{#if g.name}
			<optgroup label={g.name}>{#each g.items as option (option.value)}<option value={option.value}>{option.label}</option>{/each}</optgroup>
		{:else}
			{#each g.items as option (option.value)}<option value={option.value}>{option.label}</option>{/each}
		{/if}
	{/each}
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
