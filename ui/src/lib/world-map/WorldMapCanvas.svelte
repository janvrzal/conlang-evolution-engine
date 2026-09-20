<script lang="ts">
	import { MapPin, ZoomIn, ZoomOut, LocateFixed } from 'lucide-svelte';
	import type { WorldMapDocument, WorldMapPoint } from './types';

	let { document = null, points = [], selectedId = null, onSelect }: {
		document?: WorldMapDocument | null; points?: WorldMapPoint[]; selectedId?: string | null;
		onSelect?: (point: WorldMapPoint) => void;
	} = $props();
	let zoom = $state(1);
	let offsetX = $state(0);
	let offsetY = $state(0);

	function changeZoom(delta: number) { zoom = Math.min(2.4, Math.max(0.7, Number((zoom + delta).toFixed(2)))); }
	function resetView() { zoom = 1; offsetX = 0; offsetY = 0; }
</script>

<section class="relative min-h-[560px] overflow-hidden rounded-xl border bg-slate-950 text-white" aria-label="World map canvas">
	<div class="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_#253047_0%,_#101522_62%,_#080b12_100%)]"></div>
	<div class="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.12)_1px,transparent_1px)] [background-size:48px_48px]"></div>
	{#if document?.backgroundUrl}
		<img class="absolute inset-0 h-full w-full object-cover opacity-50" src={document.backgroundUrl} alt="Importovaný podklad světa" />
	{/if}
	<div class="absolute inset-0 transition-transform duration-200" style={`transform: translate(${offsetX}px,${offsetY}px) scale(${zoom})`}>
		<div class="absolute left-[12%] top-[22%] h-[38%] w-[26%] rounded-[45%] bg-emerald-950/50 blur-[1px]"></div>
		<div class="absolute left-[45%] top-[32%] h-[45%] w-[28%] rounded-[48%] bg-amber-950/40 blur-[1px]"></div>
		<div class="absolute left-[73%] top-[14%] h-[28%] w-[15%] rounded-[50%] bg-sky-950/45 blur-[1px]"></div>
		{#each points as point (point.id)}
			<button class:selected={selectedId === point.id} class="absolute -translate-x-1/2 -translate-y-1/2 rounded-full p-1.5 transition hover:bg-white/15" style={`left:${point.x}%;top:${point.y}%`} title={point.label} aria-label={`Vybrat ${point.label}`} onclick={() => onSelect?.(point)}>
				<MapPin class="h-5 w-5 drop-shadow-md" />
			</button>
		{/each}
	</div>
	<div class="absolute bottom-4 left-4 flex items-center gap-1 rounded-lg border border-white/15 bg-black/45 p-1 backdrop-blur">
		<button class="rounded p-2 hover:bg-white/10" title="Přiblížit" aria-label="Přiblížit" onclick={() => changeZoom(.15)}><ZoomIn class="h-4 w-4" /></button>
		<button class="rounded p-2 hover:bg-white/10" title="Oddálit" aria-label="Oddálit" onclick={() => changeZoom(-.15)}><ZoomOut class="h-4 w-4" /></button>
		<button class="rounded p-2 hover:bg-white/10" title="Výchozí pohled" aria-label="Výchozí pohled" onclick={resetView}><LocateFixed class="h-4 w-4" /></button>
	</div>
	<div class="absolute right-4 top-4 rounded-md border border-white/15 bg-black/45 px-3 py-2 text-xs text-white/70 backdrop-blur">Geografický pohled · pouze pro čtení</div>
	{#if points.length === 0}<p class="absolute inset-0 flex items-center justify-center text-sm text-white/60">Zatím nejsou rozmístěny žádné geografické body.</p>{/if}
</section>

<style>
	button.selected { color: #fbbf24; filter: drop-shadow(0 0 8px #f59e0b); }
</style>
