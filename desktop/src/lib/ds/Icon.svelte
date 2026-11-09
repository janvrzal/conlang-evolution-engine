<!-- Ikony čárou (16 px, barva textu). -->
<script lang="ts">
	export type IconName = 'undo' | 'redo' | 'play' | 'pause' | 'plus' | 'close' | 'search' | 'open' | 'save' | 'stop';
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
		stop: 'M6 6h12v12H6z'
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
