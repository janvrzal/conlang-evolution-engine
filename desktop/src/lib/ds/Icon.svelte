<!-- Ikony čárou (16 px, barva textu). Pojmy enginu viz docs/brand/README.md. -->
<script lang="ts">
	export type IconName = 'undo' | 'redo' | 'play' | 'pause' | 'plus' | 'close' | 'search' | 'open' | 'save' | 'stop'
		| 'jazyk' | 'zmena' | 'protojazyk' | 'vymreni' | 'rodina' | 'rozdeleni' | 'vesnice' | 'vypujcka' | 'mluvci' | 'nareci' | 'generace';
	let { name, size = 16 }: { name: IconName; size?: number } = $props();
	const PATHS: Record<IconName, string> = {
		undo: 'M9 14 4 9l5-5 M4 9h11a5 5 0 0 1 0 10h-3',
		redo: 'm15 14 5-5-5-5 M20 9H9a5 5 0 0 0 0 10h3',
		play: 'M7 4l13 8-13 8z',
		pause: 'M8 4v16 M16 4v16',
		plus: 'M12 5v14 M5 12h14',
		close: 'M6 6l12 12 M18 6 6 18',
		search: 'M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14 M20 20l-4-4',
		open: 'M4 6h6l2 2h8v10H4z',
		save: 'M5 4h11l3 3v13H5z M8 4v5h7V4 M8 20v-6h8v6',
		stop: 'M6 6h12v12H6z',
		// jazyk
		jazyk: 'M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-4 3.5V17H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z M9 9.2c1.4-1.6 5.5-1.4 5.5 1.6 0 2.6-2.2 3.6-3.8 3.3 M8.8 11.2h5.7',
		// zvuková změna (p > f)
		zmena: 'M4 9v11 M4 9.6c3.6-1.6 5 .4 5 2.4s-1.4 4-5 2.4 M11 10.5l3 2-3 2 M18.5 20v-9c0-2.2 1.2-3.5 3-3.5 M16.5 12.5h4',
		// protojazyk (*kořen-)
		protojazyk: 'M6.5 5v8 M3 7l7 4 M10 7l-7 4 M13.5 17.5h7',
		// vymření (†)
		vymreni: 'M12 3v18 M6 8.5h12',
		// rodina jazyků
		rodina: 'M3 12h2c3 0 3-7 6-7h9 M5 12c3 0 3 4.5 6 4.5 M11 16.5c2.2 0 2.2-3.5 4.5-3.5H18 M11 16.5c2.2 0 2.2 3.5 4.5 3.5H21',
		// rozdělení jazyka
		rozdeleni: 'M3 12h5 M8 12c3.5 0 3.5-7 7-7h6 M8 12c3.5 0 3.5 7 7 7h6',
		// vesnice
		vesnice: 'M2.5 20h19 M4 20v-9l5-4.5 5 4.5v9 M14 20v-6l3.5-3.5L21 14v6 M7.5 20v-4.5h3V20',
		// výpůjčka
		vypujcka: 'M3 6h18 M3 18h18 M8 6c4 0 4 12 8 12',
		// mluvčí
		mluvci: 'M12 4a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7 M5 20c1-4 3.8-6 7-6s6 2 7 6',
		// nářečí (izoglosa)
		nareci: 'M12 3c-2.6 3 2.6 6 0 9s2.6 6 0 9 M5.5 9.8a2.2 2.2 0 1 0 0 4.4a2.2 2.2 0 1 0 0-4.4 M16 14.3l2.5-4.5 2.5 4.5z',
		// generace (tři věky)
		generace: 'M5 11.5a1.8 1.8 0 1 0 0 3.6a1.8 1.8 0 1 0 0-3.6 M2.5 20.5c.3-2 1.2-3.3 2.5-3.3s2.2 1.3 2.5 3.3 M12 4.5a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5 M8.3 20.5c.4-4.6 1.8-8 3.7-8s3.3 3.4 3.7 8 M19 8.5a2.2 2.2 0 1 0 0 4.4a2.2 2.2 0 1 0 0-4.4 M16.6 20.5c.3-3.3 1.2-5.6 2.4-5.6s2.1 2.3 2.4 5.6'
	};
	const filled = $derived(name === 'play' || name === 'stop');
</script>

<svg class:filled viewBox="0 0 24 24" width={size} height={size} aria-hidden="true"><path d={PATHS[name]} /></svg>

<style>
	svg {
		fill: none;
		stroke: currentColor;
		stroke-width: 1.6;
		stroke-linecap: round;
		stroke-linejoin: round;
		flex: none;
	}
	svg.filled {
		fill: currentColor;
		stroke: none;
	}
</style>
