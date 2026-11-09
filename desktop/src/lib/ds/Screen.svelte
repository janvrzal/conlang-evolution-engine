<!-- Mřížka obrazovky. Sloupce i řádky se zadávají jako šířky: číslo = px, 'fill' = zbytek. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	type Track = number | 'fill' | 'auto';
	let { columns = ['fill'], rows, label, children }: { columns?: Track[]; rows?: Track[]; label?: string; children: Snippet } = $props();
	const track = (t: Track) => (t === 'fill' ? 'minmax(0, 1fr)' : t === 'auto' ? 'auto' : `${t}px`);
	const cols = $derived(columns.map(track).join(' '));
	const rws = $derived(rows ? rows.map(track).join(' ') : 'minmax(0, 1fr)');
</script>

<div class="screen" aria-label={label} style:grid-template-columns={cols} style:grid-template-rows={rws}>
	{@render children()}
</div>

<style>
	.screen {
		flex: 1 1 auto;
		display: grid;
		gap: 12px 16px;
		padding: 12px 16px;
		min-height: 0;
	}
	@media (max-width: 900px) {
		.screen {
			grid-template-columns: minmax(0, 1fr) !important;
			grid-template-rows: auto !important;
		}
	}
</style>
