<!-- Zaškrtávátko s popiskem; volitelně značka a počet vpravo (filtry kroniky).
     Políčko je nativní <input> (klávesnice, čtečky); háček se při zaškrtnutí dokreslí tahem. -->
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
	<span class="box">
		<input type="checkbox" bind:checked onchange={() => onchange?.(checked)} />
		<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.6 8.4l2.9 2.9 5.9-6.6" /></svg>
	</span>
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
		transition: background var(--t-tick);
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
	.box {
		position: relative;
		display: inline-grid;
		flex: none;
		width: 16px;
		height: 16px;
	}
	input {
		appearance: none;
		margin: 0;
		width: 16px;
		height: 16px;
		border: 1.5px solid var(--ink-2);
		border-radius: var(--radius);
		background: var(--land);
		cursor: pointer;
		transition:
			background var(--t-snap) var(--e-change),
			border-color var(--t-snap) var(--e-change);
	}
	input:checked {
		background: var(--ink);
		border-color: var(--ink);
	}
	svg {
		position: absolute;
		inset: 0;
		width: 16px;
		height: 16px;
		pointer-events: none;
	}
	path {
		fill: none;
		stroke: var(--land);
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-dasharray: 16;
		stroke-dashoffset: 16;
		transition: stroke-dashoffset var(--t-snap) var(--e-arrive);
	}
	input:checked + svg path {
		stroke-dashoffset: 0;
		transition-delay: 40ms;
	}
</style>
