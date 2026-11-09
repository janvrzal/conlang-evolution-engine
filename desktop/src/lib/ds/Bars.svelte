<!-- Vodorovné pruhy: každý řádek má popisek, složený pruh (podíly 0–1 s barvou) a hodnotu. -->
<script lang="ts">
	export interface BarRow {
		label: string;
		segments: { value: number; color: string; label?: string }[];
		value: string;
	}
	let { rows, labelWidth = 124, label }: { rows: BarRow[]; labelWidth?: number; label?: string } = $props();
</script>

<div class="bars" role="list" aria-label={label}>
	{#each rows as row, i (i)}
		<div class="row" role="listitem" style:grid-template-columns="{labelWidth}px minmax(0, 1fr) 64px">
			<span class="label">{row.label}</span>
			<span class="track" aria-hidden="true">
				{#each row.segments as segment, k (k)}<span style:width="{Math.max(0, Math.min(1, segment.value)) * 100}%" style:background={segment.color} title={segment.label}></span>{/each}
			</span>
			<span class="value">{row.value}</span>
		</div>
	{/each}
</div>

<style>
	.bars {
		display: grid;
		gap: 6px;
	}
	.row {
		display: grid;
		gap: 8px;
		align-items: center;
		font-size: 13px;
	}
	.label {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.track {
		height: 10px;
		background: var(--field);
		border-radius: 1px;
		overflow: hidden;
		display: flex;
	}
	.track span {
		display: block;
		height: 100%;
	}
	.value {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
</style>
