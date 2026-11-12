<!-- Rodokmen jazyků: evoluční strom rodiny (nebo všech rodin pod sebou). Osa x = čas, tloušťka konce
     = mluvčí dnes, vymřelý jazyk se zúží do vlásečnice s † rokem. Barvy jako řeka a mapa; vybraný
     jazyk má obrys inkoustem. Strom při zobrazení vyroste zleva doprava. -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { Tween } from 'svelte/motion';
	import { familyTree, type TreeLineage } from './familyTree';
	import { formatYear } from './format';
	import { T, arrive, still } from './motion';

	export interface TreeItem extends TreeLineage {
		label: string;
		color: string;
	}
	let {
		items,
		now,
		cursor,
		selected = null,
		label,
		onselect
	}: { items: TreeItem[]; now: number; cursor?: number; selected?: string | null; label: string; onselect?: (id: string) => void } = $props();

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

	const LEFT = 24, RIGHT = 170, TOP = 32, BOTTOM = 34;
	const model = $derived.by(() => {
		if (!w || !h || !items.length) return null;
		const rows = items.length + 1;
		const rowH = Math.max(12, Math.min(30, (h - TOP - BOTTOM) / rows));
		const lay = familyTree(items, now, Math.max(100, w - LEFT - RIGHT), rowH);
		const unit = lay.to - lay.from > 2000 ? 500 : 250, ticks: number[] = [];
		for (let t = Math.ceil(lay.from / unit) * unit; t <= lay.to; t += unit) ticks.push(t);
		return { ...lay, ticks, byId: new Map(items.map((i) => [i.id, i])) };
	});
	const svgH = $derived(model ? Math.max(h, model.height + TOP + BOTTOM) : h);

	// růst zleva doprava při zobrazení a při jiném souboru jazyků
	const reveal = new Tween(0, { easing: arrive });
	let grown = '';
	$effect(() => {
		const key = items.map((i) => i.id).join('|');
		if (!w || !items.length || key === grown) return;
		grown = key;
		reveal.set(0, { duration: 0 });
		reveal.set(1, { duration: still() ? 0 : T.epoch * 1.5 });
	});
	const uid = $props.id();
	function key(event: KeyboardEvent, id: string) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			onselect?.(id);
		}
	}
</script>

<div class="tree" bind:this={box}>
	{#if model}
		<svg width={w} height={svgH} role="group" aria-label={label}>
			{#each model.ticks as t (t)}
				<line x1={LEFT + model.x(t)} x2={LEFT + model.x(t)} y1="4" y2={svgH - 24} class="grid" />
				<text x={LEFT + model.x(t)} y={svgH - 8} class="tick">{formatYear(t)}</text>
			{/each}
			<clipPath id="{uid}-grow"><rect x="0" y="0" width={LEFT + reveal.current * (w - LEFT)} height={svgH} /></clipPath>
			<g clip-path="url(#{uid}-grow)" transform="translate({LEFT} {TOP})">
				{#each model.branches as b (b.id)}
					{@const it = model.byId.get(b.id)}
					<path
						d={b.d}
						fill={it?.color ?? 'var(--ink-2)'}
						class:sel={b.id === selected}
						role="button"
						tabindex="0"
						aria-label={it?.label}
						onclick={() => onselect?.(b.id)}
						onkeydown={(e) => key(e, b.id)}><title>{it?.label}{it?.end != null ? ` † ${formatYear(it.end)}` : ''}</title></path
					>
					<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
					<text x={b.x + 8} y={b.y + 4} class="name" class:sel={b.id === selected} class:gone={b.extinct} onclick={() => onselect?.(b.id)}
						>{#if b.extinct}{`† ${formatYear(it?.end ?? 0)} · `}{/if}{it?.label}</text
					>
				{/each}
			</g>
			{#if cursor != null && cursor < model.to}<line x1={LEFT + model.x(cursor)} x2={LEFT + model.x(cursor)} y1="4" y2={svgH - 26} class="cursor" />{/if}
		</svg>
	{/if}
</div>

<style>
	.tree {
		position: absolute;
		inset: 0;
		overflow: auto;
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
		cursor: pointer;
		stroke: none;
		transition: stroke-width var(--t-snap) var(--e-change);
	}
	path.sel,
	path:focus-visible {
		outline: none;
		stroke: var(--ink);
		stroke-width: 1.6;
	}
	.name {
		font-size: 12.5px;
		font-family: var(--f-ipa);
		font-style: italic;
		fill: var(--ink);
		cursor: pointer;
	}
	.name.gone {
		fill: var(--ink-2);
		font-size: 11.5px;
	}
	.name.sel {
		font-weight: 700;
	}
	.cursor {
		stroke: var(--ink);
		stroke-width: 1.5;
	}
</style>
