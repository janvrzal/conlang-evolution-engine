<!-- Malý sloupcový graf (vsí s rozdílem v čase). Nulové sloupce jsou šedé, ostatní červené. -->
<script lang="ts">
	let { values, labels, label, height = 64 }: { values: number[]; labels: string[]; label: string; height?: number } = $props();
	const max = $derived(Math.max(1, ...values));
</script>

<div class="wrap">
	<div class="curve" role="img" aria-label={label} style:height="{height}px" style:grid-template-columns="repeat({values.length}, minmax(0, 1fr))">
		{#each values as v, i (i)}<span class:z={v === 0} style:height="{v === 0 ? 2 : (v / max) * 100}%"></span>{/each}
	</div>
	<div class="x" aria-hidden="true" style:grid-template-columns="repeat({values.length}, minmax(0, 1fr))">
		{#each labels as l, i (i)}<span>{l}</span>{/each}
	</div>
</div>

<style>
	.wrap {
		display: grid;
		gap: 4px;
	}
	.curve {
		display: grid;
		gap: 6px;
		align-items: end;
		border-bottom: 1px solid var(--ink-2);
		padding: 0 2px;
	}
	.curve span {
		display: block;
		background: var(--red);
		border-radius: 1px 1px 0 0;
	}
	.curve span.z {
		background: var(--rule);
	}
	.x {
		display: grid;
		gap: 6px;
		font-size: 11px;
		color: var(--ink-2);
		text-align: center;
		font-variant-numeric: tabular-nums;
	}
</style>
