<!-- Vrt: co se v místě říkalo, od nejnovějšího. Červený okraj = změna jazyka, ne jen výslovnosti. -->
<script lang="ts">
	export interface Stratum {
		form: string;
		note: string;
		changed?: boolean;
	}
	let { items, label }: { items: Stratum[]; label?: string } = $props();
</script>

<ol class="strata" aria-label={label}>
	{#each items as item, i (i)}
		<li class:chg={item.changed}><span class="ipa">{item.form}</span><small>{item.note}</small></li>
	{/each}
</ol>

<style>
	.strata {
		list-style: none;
		margin: 0;
		padding: 0;
		border-left: 2px solid var(--ink);
		display: grid;
	}
	li {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 8px;
		padding: 6px 10px;
		border-bottom: 1px solid var(--rule);
		align-items: baseline;
	}
	.chg {
		box-shadow: inset 3px 0 0 var(--red);
	}
	.ipa {
		font-family: var(--f-ipa);
		font-size: 18px;
	}
	small {
		font-size: 13px;
		color: var(--ink-2);
		font-style: italic;
		font-variant-numeric: tabular-nums;
	}
</style>
