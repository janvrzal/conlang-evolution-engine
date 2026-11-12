<!-- Úvodní animace při spuštění: E se nadechne a vyroste do rodokmenu, kamera se oddaluje, část větví
     vymře, na konci projde vlna a objeví se nápis. Klik nebo klávesa ji přeskočí; při omezeném pohybu
     se nehraje. Obrazovka dodá texty a co se stane po skončení (onend). -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { splash } from './brand';
	import { narrow, still } from './motion';

	let {
		generation,
		title = 'CEE',
		subtitle,
		onend
	}: {
		/** text počítadla generací, např. (n) => `generace ${n}` */
		generation: (n: number) => string;
		title?: string;
		subtitle: string;
		onend: () => void;
	} = $props();

	const anim = splash();
	let f = $state(anim.frame(0));
	let raf = 0;
	let ended = false;
	function end() {
		if (ended) return;
		ended = true;
		cancelAnimationFrame(raf);
		onend();
	}
	onMount(() => {
		if (still()) {
			end();
			return;
		}
		const t0 = performance.now();
		const step = (now: number) => {
			const t = (now - t0) / 1000;
			f = anim.frame(t);
			if (t < anim.length + 0.6) raf = requestAnimationFrame(step);
			else end();
		};
		raf = requestAnimationFrame(step);
		return () => cancelAnimationFrame(raf);
	});
</script>

<svelte:window onkeydown={end} />

<!-- Celá plocha je jen přeskočitelná ozdoba; přeskočit jde i klávesou. -->
<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="splash" onclick={end} out:narrow={{ duration: 280 }}>
	<div class="stage">
		<span class="gen" style:opacity={1 - f.text}>{generation(f.generation)}</span>
		<svg viewBox={f.view.join(' ') + ' ' + f.view[2]} aria-hidden="true"><path d={f.d} /></svg>
		<div class="word" style:opacity={f.text} style:transform="translateY({(1 - f.text) * 6}px)">
			<span class="title">{title}</span>
			<span class="sub">{subtitle}</span>
		</div>
	</div>
</div>

<style>
	.splash {
		position: fixed;
		inset: 0;
		z-index: 100;
		display: grid;
		place-items: center;
		background: var(--land);
		color: var(--ink);
		cursor: pointer;
	}
	.stage {
		position: relative;
		width: min(60vmin, 420px);
	}
	svg {
		display: block;
		width: 100%;
		aspect-ratio: 1;
	}
	path {
		fill: currentColor;
	}
	.gen {
		position: absolute;
		left: 4px;
		top: -8px;
		font: italic 14px var(--f-ipa);
		color: var(--ink-2);
		font-variant-numeric: tabular-nums;
	}
	.word {
		display: grid;
		justify-items: center;
		gap: 2px;
		margin-top: 6px;
		font-family: var(--f-ipa);
	}
	.title {
		font-size: 34px;
		letter-spacing: 0.08em;
		line-height: 1;
	}
	.sub {
		font-size: 15px;
		font-style: italic;
		color: var(--ink-2);
	}
</style>
