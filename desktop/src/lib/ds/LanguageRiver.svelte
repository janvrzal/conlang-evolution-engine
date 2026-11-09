<!-- Řeka jazyků: proudy podle počtu mluvčích doma v čase (šířka), seskupené po rodinách.
     Nový proud = rozštěpení. Popisky jen u proudů, kam se vejdou; ostatní v titulku na najetí. -->
<script lang="ts">
	import { area, curveMonotoneX, stack, stackOffsetSilhouette, stackOrderNone } from 'd3-shape';
	import { onMount } from 'svelte';

	export interface RiverStream {
		id: string;
		label: string;
		color: string;
		/** mluvčí doma v jednotlivých letech (stejná délka jako years) */
		values: number[];
		/** rok zániku, pokud jazyk vymřel */
		end?: number | null;
	}
	let {
		years,
		streams,
		selected = null,
		cursor,
		label,
		dimmed = null,
		onselect
	}: {
		years: number[];
		streams: RiverStream[];
		selected?: string | null;
		cursor?: number;
		label: string;
		/** proudy, které filtr nevybral: zůstanou v řece, ale ztlumené */
		dimmed?: Set<string> | null;
		onselect?: (id: string) => void;
	} = $props();

	let box: HTMLDivElement;
	let w = $state(0);
	let h = $state(0);
	onMount(() => {
		const ro = new ResizeObserver(() => {
			w = box.clientWidth;
			h = box.clientHeight;
		});
		ro.observe(box);
		return () => ro.disconnect();
	});

	const model = $derived.by(() => {
		if (!w || !h || years.length < 2 || !streams.length) return null;
		const rows = years.map((y, i) => Object.fromEntries([['y', y], ...streams.map((s) => [s.id, s.values[i] ?? 0])])) as Record<string, number>[];
		const layers = stack<Record<string, number>>().keys(streams.map((s) => s.id)).offset(stackOffsetSilhouette).order(stackOrderNone)(rows);
		const y0 = years[0], y1 = years[years.length - 1];
		let lo = Infinity, hi = -Infinity;
		for (const l of layers) for (const d of l) {
			lo = Math.min(lo, d[0]);
			hi = Math.max(hi, d[1]);
		}
		const x = (y: number) => 40 + ((y - y0) / (y1 - y0)) * (w - 190);
		const sy = (v: number) => h - 30 - ((v - lo) / (hi - lo || 1)) * (h - 46);
		const shape = area<[number, number] & { data: Record<string, number> }>()
			.x((d) => x(d.data.y))
			.y0((d) => sy(d[0]))
			.y1((d) => sy(d[1]))
			.curve(curveMonotoneX);
		const byId = new Map(streams.map((s) => [s.id, s]));
		const paths = layers.map((l) => ({ id: l.key, d: shape(l as never) ?? '', stream: byId.get(l.key)! }));
		// popisky na konci živých proudů, aby se nepřekrývaly
		const ends = layers
			.map((l) => {
				const e = l[l.length - 1];
				return { id: l.key, y: sy((e[0] + e[1]) / 2), alive: e[1] - e[0] > 0 };
			})
			.filter((l) => l.alive)
			.sort((a, b) => a.y - b.y);
		const shown: { id: string; y: number }[] = [];
		for (const l of ends) {
			const prev = shown[shown.length - 1], yy = prev ? Math.max(l.y, prev.y + 15) : l.y;
			if (l.id === selected || yy - l.y < 10) shown.push({ id: l.id, y: yy });
		}
		const ticks: number[] = [];
		const unit = y1 - y0 > 2000 ? 500 : 250;
		for (let t = Math.ceil(y0 / unit) * unit; t <= y1; t += unit) ticks.push(t);
		return { paths, shown, ticks, x, xEnd: x(y1), byId };
	});
	function key(event: KeyboardEvent, id: string) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			onselect?.(id);
		}
	}
</script>

<div class="river" bind:this={box}>
	{#if model}
		<svg width={w} height={h} role="group" aria-label={label}>
			{#each model.ticks as t (t)}
				<line x1={model.x(t)} x2={model.x(t)} y1="10" y2={h - 24} class="grid" />
				<text x={model.x(t)} y={h - 8} class="tick">{t}</text>
			{/each}
			{#each model.paths as p (p.id)}
				<path
					d={p.d}
					fill={p.stream.color}
					class:sel={p.id === selected}
					class:dim={dimmed?.has(p.id) && p.id !== selected}
					role="button"
					tabindex="0"
					aria-label={p.stream.label}
					onclick={() => onselect?.(p.id)}
					onkeydown={(e) => key(e, p.id)}><title>{p.stream.label}{p.stream.end ? ` † ${p.stream.end}` : ''}</title></path
				>
			{/each}
			{#each model.shown as l (l.id)}
				<text x={model.xEnd + 8} y={l.y + 4} class="name" class:sel={l.id === selected}>{model.byId.get(l.id)?.label}</text>
			{/each}
			{#if cursor != null}<line x1={model.x(cursor)} x2={model.x(cursor)} y1="8" y2={h - 26} class="cursor" />{/if}
		</svg>
	{/if}
</div>

<style>
	.river {
		position: absolute;
		inset: 0;
	}
	svg {
		display: block;
	}
	.grid {
		stroke: var(--rule);
	}
	.tick {
		font-size: 11px;
		text-anchor: middle;
		fill: var(--ink-2);
		font-variant-numeric: tabular-nums;
	}
	path {
		fill-opacity: 0.6;
		stroke: var(--land);
		stroke-width: 0.8;
		cursor: pointer;
	}
	path.sel {
		fill-opacity: 0.95;
		stroke: var(--ink);
		stroke-width: 2;
	}
	path.dim {
		fill-opacity: 0.15;
	}
	path:focus-visible {
		outline: none;
		stroke: var(--ink);
		stroke-width: 2;
	}
	.name {
		font-size: 12.5px;
		fill: var(--ink);
		cursor: default;
	}
	.name.sel {
		font-weight: 700;
	}
	.cursor {
		stroke: var(--ink);
		stroke-width: 1.5;
	}
</style>
