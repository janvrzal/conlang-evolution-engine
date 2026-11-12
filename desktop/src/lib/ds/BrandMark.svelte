<!-- Značka CEE (měkký rodokmen ve tvaru E) v barvě textu. Stavy (mode):
     mark = klid, idle = nadechování (prázdný projekt), wave = vlna po doběhnutí běhu,
     done = celý rodokmen s vlnou (dosimulováno), wither = uschlá spodní větev (běh selhal),
     progress = rodokmen podle postupu běhu. Jednorázové stavy se přehrají při zobrazení. -->
<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { done, idle, mark, progress as grow, wave, wither, type Frame } from './brand';
	import { still } from './motion';

	let {
		mode = 'mark',
		progress = 0,
		size = 24,
		label
	}: {
		mode?: 'mark' | 'idle' | 'wave' | 'done' | 'wither' | 'progress';
		/** 0–1 pro mode = progress */
		progress?: number;
		size?: number;
		/** popisek pro čtečky; bez něj je značka jen ozdoba */
		label?: string;
	} = $props();

	type Mode = 'mark' | 'idle' | 'wave' | 'done' | 'wither' | 'progress';
	const at = (s: Mode, t: number): Frame =>
		s === 'idle' ? idle(t) : s === 'wave' ? wave(t) : s === 'done' ? done(t) : s === 'wither' ? wither(t) : s === 'progress' ? grow(progress) : mark();
	const length = (s: Mode) => (s === 'wave' ? 1.1 : s === 'done' ? 1.5 : s === 'wither' ? 1.3 : s === 'idle' ? Infinity : 0);
	const final = (s: Mode) => at(s, s === 'idle' ? 0 : 3);

	let f = $state<Frame>(final(untrack(() => mode)));
	let raf = 0;
	function play(s: Mode) {
		cancelAnimationFrame(raf);
		const len = length(s);
		if (!len || still()) {
			f = final(s);
			return;
		}
		const t0 = performance.now();
		const step = (now: number) => {
			const t = (now - t0) / 1000;
			f = at(s, Math.min(t, len));
			if (t < len) raf = requestAnimationFrame(step);
		};
		raf = requestAnimationFrame(step);
	}
	let mounted = false;
	$effect(() => {
		const s = mode;
		if (s === 'progress') {
			f = grow(progress);
			return;
		}
		if (mounted) play(s);
	});
	onMount(() => {
		mounted = true;
		play(mode);
		return () => cancelAnimationFrame(raf);
	});
</script>

<svg
	class="mark"
	width={size}
	height={size}
	viewBox={f.view.join(' ') + ' ' + f.view[2]}
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}><path d={f.d} /></svg
>

<style>
	.mark {
		display: inline-block;
		flex: none;
		vertical-align: middle;
		overflow: visible;
	}
	path {
		fill: currentColor;
	}
</style>
