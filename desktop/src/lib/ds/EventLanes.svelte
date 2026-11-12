<!-- Kronika zadání: pruhy (Státy, Jazyk ve společnosti, Lidé a místa, Hlásky) s událostmi na ose let.
     Rámeček = studijní případ, červeně = vybraná nebo chybná. ←/→ přechází mezi událostmi pruhu. -->
<script lang="ts">
	import { untrack } from 'svelte';
	import { formatYear } from './format';
	import { T, still } from './motion';
	export interface LaneEvent {
		id: string | number;
		year: number;
		label: string;
		state?: 'selected' | 'case' | 'bad';
	}
	export interface Lane {
		id: string;
		label: string;
		events: LaneEvent[];
		/** text, když pruh nemá události */
		empty?: string;
		muted?: boolean;
	}
	let {
		start,
		end,
		lanes,
		cursor,
		label,
		onselect
	}: { start: number; end: number; lanes: Lane[]; cursor?: number; label: string; onselect?: (event: LaneEvent, lane: Lane) => void } = $props();

	// Událost, přes kterou při přehrávání přejde ukazatel, krátce vyraší (velké skoky ukazatele ne).
	let prev: number | undefined;
	let passing = $state(new Set<string>());
	$effect(() => {
		const c = cursor, p = prev;
		prev = c;
		if (c == null || p == null || still() || c <= p || c - p > (end - start) * 0.1) return;
		const hit: string[] = [];
		for (const lane of untrack(() => lanes)) for (const ev of lane.events) if (ev.year > p && ev.year <= c) hit.push(`${lane.id}:${ev.id}`);
		if (!hit.length) return;
		passing = new Set([...untrack(() => passing), ...hit]);
		setTimeout(() => {
			const next = new Set(passing);
			hit.forEach((k) => next.delete(k));
			passing = next;
		}, T.flow);
	});

	const pct = (y: number) => ((y - start) / (end - start || 1)) * 100;
	const ticks = $derived.by(() => {
		const span = end - start, unit = span > 2000 ? 500 : span > 800 ? 250 : 100, out: number[] = [];
		for (let y = Math.ceil(start / unit) * unit; y <= end; y += unit) out.push(y);
		return out;
	});
	function key(event: KeyboardEvent, lane: Lane, index: number) {
		const next = event.key === 'ArrowRight' ? index + 1 : event.key === 'ArrowLeft' ? index - 1 : null;
		if (next == null || next < 0 || next >= lane.events.length) return;
		event.preventDefault();
		const row = (event.currentTarget as HTMLElement).parentElement;
		(row?.children[next] as HTMLElement | undefined)?.focus();
	}
</script>

<div class="lanes" role="group" aria-label={label}>
	<div class="lane rul" aria-hidden="true"><span></span><div class="in">{#each ticks as y (y)}<span class="tk" style:left="{pct(y)}%">{formatYear(y)}</span>{/each}</div></div>
	{#each lanes as lane (lane.id)}
		{@const sorted = [...lane.events].sort((a, b) => a.year - b.year)}
		<div class="lane">
			<span class="name" class:muted={lane.muted}>{lane.label}</span>
			<div class="in">
				{#if cursor != null}<span class="cur" style:left="{pct(cursor)}%" aria-hidden="true"></span>{/if}
				{#if sorted.length}
					{#each sorted as ev, i (ev.id)}
						<button
							type="button"
							class="ev {ev.state ?? ''}"
							class:pass={passing.has(`${lane.id}:${ev.id}`)}
							style:left="{pct(ev.year)}%"
							aria-label="{formatYear(ev.year)} {ev.label}"
							title="{formatYear(ev.year)} {ev.label}"
							aria-pressed={ev.state === 'selected'}
							onclick={() => onselect?.(ev, lane)}
							onkeydown={(e) => key(e, lane, i)}><i></i></button
						>
					{/each}
				{:else if lane.empty}
					<span class="empty">{lane.empty}</span>
				{/if}
			</div>
		</div>
	{/each}
</div>

<style>
	.lanes {
		display: grid;
		min-width: 0;
	}
	.lane {
		display: grid;
		grid-template-columns: 160px minmax(0, 1fr);
		align-items: center;
		min-height: 30px;
		border-bottom: 1px solid var(--rule);
	}
	.rul {
		min-height: 22px;
		border-bottom-color: var(--ink);
	}
	.name {
		font-size: 13px;
	}
	.muted {
		color: var(--ink-2);
		font-style: italic;
	}
	.in {
		position: relative;
		height: 30px;
	}
	.rul .in {
		height: 22px;
	}
	.tk {
		position: absolute;
		top: 2px;
		transform: translateX(-50%);
		font-size: 11px;
		color: var(--ink-2);
		font-variant-numeric: tabular-nums;
	}
	.cur {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--ink);
		z-index: 1;
		pointer-events: none;
	}
	.ev {
		position: absolute;
		top: 3px;
		width: 24px;
		height: 24px;
		margin-left: -12px;
		display: grid;
		place-items: center;
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
		z-index: 2;
	}
	.ev i {
		display: block;
		width: 7px;
		height: 13px;
		background: var(--ink);
		border-radius: 1px;
		transform-origin: 50% 100%;
	}
	.ev.pass i {
		animation: sprout var(--t-flow) var(--e-arrive);
	}
	@keyframes sprout {
		25% {
			transform: scale(1.35, 1.6);
		}
	}
	.ev.case i {
		background: none;
		border: 2px solid var(--ink);
		width: 9px;
	}
	.ev.selected i,
	.ev.bad i {
		width: 9px;
		background: var(--red);
		box-shadow:
			0 0 0 2px var(--panel),
			0 0 0 3.5px var(--red);
	}
	.empty {
		position: absolute;
		inset: 0;
		z-index: 3;
		padding-left: 6px;
		background: var(--panel);
		display: flex;
		align-items: center;
		font-size: 13px;
		color: var(--ink-2);
		font-style: italic;
	}
</style>
