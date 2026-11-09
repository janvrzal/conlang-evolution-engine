<!-- Časová osa Výsledku: přehrát, hodiny, stopa s hustotou změn, značkami událostí a kurzorem, souhrn.
     Klávesy: ←/→ krok, PageUp/PageDown 10 kroků, Home/End. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onDestroy } from 'svelte';
	import Icon from './Icon.svelte';
	import { formatYear } from './format';

	export interface AxisMarker {
		year: number;
		label: string;
		/** event = dějiny autora, lang = jazyk (kosočtverec), branch = větvení (červeně) */
		kind?: 'event' | 'lang' | 'branch';
	}
	let {
		start,
		end,
		value = $bindable(),
		step = 25,
		until,
		density = [],
		markers = [],
		label,
		clockNote,
		playLabel,
		pauseLabel,
		staleFrom,
		branchFrom,
		summary,
		onchange
	}: {
		start: number;
		end: number;
		value: number;
		step?: number;
		/** spočítáno do roku (při běhu); za ním je osa tečkovaná */
		until?: number;
		/** hustota změn po úsecích, 0–1 */
		density?: number[];
		markers?: AxisMarker[];
		label: string;
		clockNote?: string;
		playLabel: string;
		pauseLabel: string;
		/** výsledky od roku jsou zastaralé (šrafa) */
		staleFrom?: number;
		/** větev se liší od roku (červený úsek) */
		branchFrom?: number;
		summary?: Snippet;
		onchange?: (year: number) => void;
	} = $props();

	let track: HTMLDivElement;
	let playing = $state(false);
	let timer: ReturnType<typeof setInterval> | null = null;
	const limit = $derived(until ?? end);
	const pct = (y: number) => ((y - start) / (end - start || 1)) * 100;
	const ticks = $derived.by(() => {
		const span = end - start, unit = span > 2000 ? 500 : span > 800 ? 250 : 100, out: number[] = [];
		for (let y = Math.ceil(start / unit) * unit; y <= end; y += unit) out.push(y);
		return out;
	});

	function set(year: number) {
		const snapped = Math.round((year - start) / step) * step + start;
		const next = Math.max(start, Math.min(limit, snapped));
		if (next !== value) {
			value = next;
			onchange?.(next);
		}
	}
	function fromPointer(event: PointerEvent) {
		const r = track.getBoundingClientRect();
		set(start + ((event.clientX - r.left) / r.width) * (end - start));
	}
	function down(event: PointerEvent) {
		if ((event.target as HTMLElement).closest('button')) return;
		track.setPointerCapture(event.pointerId);
		fromPointer(event);
	}
	function move(event: PointerEvent) {
		if (track.hasPointerCapture(event.pointerId)) fromPointer(event);
	}
	function key(event: KeyboardEvent) {
		const moves: Record<string, number> = { ArrowRight: step, ArrowLeft: -step, ArrowUp: step, ArrowDown: -step, PageUp: step * 10, PageDown: -step * 10 };
		if (event.key in moves) set(value + moves[event.key]);
		else if (event.key === 'Home') set(start);
		else if (event.key === 'End') set(limit);
		else return;
		event.preventDefault();
	}
	function toggle() {
		if (playing) return stop();
		if (value >= limit) set(start);
		playing = true;
		timer = setInterval(() => {
			if (value >= limit) stop();
			else set(value + step);
		}, 280);
	}
	function stop() {
		playing = false;
		if (timer) clearInterval(timer);
		timer = null;
	}
	onDestroy(stop);
</script>

<footer class="axis" aria-label={label}>
	<button type="button" class="play" aria-label={playing ? pauseLabel : playLabel} onclick={toggle}><Icon name={playing ? 'pause' : 'play'} size={14} /></button>
	<div class="clock"><b>{formatYear(value)}</b>{#if clockNote}<small>{clockNote}</small>{/if}</div>
	<div
		class="track"
		bind:this={track}
		role="slider"
		tabindex="0"
		aria-label={label}
		aria-valuemin={start}
		aria-valuemax={end}
		aria-valuenow={Math.round(value)}
		onpointerdown={down}
		onpointermove={move}
		onkeydown={key}
	>
		{#if density.length}
			<div class="density" aria-hidden="true">{#each density as d, i (i)}<span style:height="{Math.max(0.04, d) * 100}%"></span>{/each}</div>
		{/if}
		{#if until != null && until < end}
			<div class="line" style:right="{100 - pct(until)}%"></div>
			<div class="line dotted" style:left="{pct(until)}%"></div>
		{:else}
			<div class="line"></div>
		{/if}
		{#if staleFrom != null}<span class="stale" style:left="{pct(staleFrom)}%" aria-hidden="true"></span>{/if}
		{#if branchFrom != null}<span class="branch" style:left="{pct(branchFrom)}%" aria-hidden="true"></span>{/if}
		{#each markers as m, i (i)}
			<button
				type="button"
				class="mk {m.kind ?? 'event'}"
				style:left="{pct(m.year)}%"
				aria-label="{formatYear(m.year)} {m.label}"
				title="{formatYear(m.year)} {m.label}"
				onclick={() => set(m.year)}><i></i></button
			>
		{/each}
		<div class="cursor" style:left="{pct(value)}%"><b class:flip={pct(value) > 92}>{formatYear(value)}</b></div>
		<div class="ticks" aria-hidden="true">{#each ticks as y (y)}<span style:left="{pct(y)}%">{formatYear(y)}</span>{/each}</div>
	</div>
	<div class="tsum">{#if summary}{@render summary()}{/if}</div>
</footer>

<style>
	.axis {
		display: grid;
		grid-template-columns: auto auto minmax(0, 1fr) auto;
		gap: 14px;
		align-items: center;
		padding: 8px 16px 10px;
		border-top: 1px solid var(--rule);
	}
	.play {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		border: 1px solid var(--ink-2);
		background: none;
		display: grid;
		place-items: center;
		cursor: pointer;
		color: var(--ink);
	}
	.clock {
		min-width: 74px;
	}
	.clock b {
		display: block;
		font-size: 26px;
		font-weight: 500;
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.clock small {
		font-size: 12px;
		color: var(--ink-2);
		font-style: italic;
	}
	.track {
		position: relative;
		height: 54px;
		cursor: pointer;
		touch-action: none;
	}
	.density {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		height: 16px;
		display: flex;
		align-items: flex-end;
		gap: 2px;
	}
	.density span {
		flex: 1;
		background: var(--rule);
		border-radius: 1px 1px 0 0;
	}
	.line {
		position: absolute;
		left: 0;
		right: 0;
		top: 24px;
		border-top: 1px solid var(--ink-2);
	}
	.dotted {
		border-top-style: dotted;
	}
	.stale {
		position: absolute;
		right: 0;
		top: 18px;
		height: 12px;
		background: repeating-linear-gradient(45deg, var(--red) 0 1px, transparent 1px 5px);
		opacity: 0.8;
	}
	.branch {
		position: absolute;
		right: 0;
		top: 22px;
		height: 4px;
		background: var(--tint);
		border-top: 1px dashed var(--red);
	}
	.mk {
		position: absolute;
		top: 14px;
		width: 24px;
		height: 24px;
		margin-left: -12px;
		display: grid;
		place-items: center;
		background: none;
		border: 0;
		padding: 0;
		cursor: pointer;
	}
	.mk i {
		display: block;
		width: 8px;
		height: 8px;
		background: var(--ink);
	}
	.mk.lang i {
		transform: rotate(45deg);
		width: 7px;
		height: 7px;
		border: 1.5px solid var(--panel);
		outline: 1px solid var(--ink);
	}
	.mk.branch i {
		background: var(--red);
	}
	.cursor {
		position: absolute;
		top: 4px;
		bottom: 14px;
		width: 2px;
		margin-left: -1px;
		background: var(--ink);
		pointer-events: none;
	}
	.cursor b {
		position: absolute;
		top: -2px;
		left: 6px;
		font-size: 11px;
		font-weight: 500;
		font-variant-numeric: tabular-nums;
	}
	.cursor b.flip {
		left: auto;
		right: 6px;
	}
	.ticks {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 14px;
		font-size: 11px;
		color: var(--ink-2);
		font-variant-numeric: tabular-nums;
	}
	.ticks span {
		position: absolute;
		transform: translateX(-50%);
	}
	.tsum {
		font-size: 13px;
		color: var(--ink-2);
		max-width: 280px;
	}
	.tsum :global(b) {
		color: var(--ink);
		font-weight: 500;
	}
</style>
