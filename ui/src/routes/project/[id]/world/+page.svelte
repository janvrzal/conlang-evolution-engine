<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { ArrowLeft, BookOpen, Layers3, Map as MapIcon } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import WorldMapCanvas from '$lib/world-map/WorldMapCanvas.svelte';
	import WorldLayersPanel from '$lib/world-map/WorldLayersPanel.svelte';
	import WorldInspector from '$lib/world-map/WorldInspector.svelte';
	import WorldMapImportPanel from '$lib/world-map/WorldMapImportPanel.svelte';
	import { onMount } from 'svelte';
	import { loadProject, projectState, updateWorldMap, setWorldMapLayer } from '$lib/state.svelte';
	import type { WorldMapDocument, WorldMapPoint } from '$lib/world-map/types';

	let selected = $state<WorldMapPoint | null>(null);
	let ready = $state(false);
	let document = $derived<WorldMapDocument>({ ...projectState.worldModel.map.document, backgroundUrl: projectState.worldModel.map.document.backgroundDataUrl });
	let points = $derived<WorldMapPoint[]>(projectState.worldModel.map.points);
	let layers = $derived(projectState.worldModel.map.layers);

	onMount(async () => {
		await loadProject($page.params.id ?? 'default');
		ready = true;
	});
</script>

<svelte:head><title>CEE | Světová mapa</title></svelte:head>

{#if !ready}
	<div class="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Načítám světovou mapu…</div>
{:else}
<div class="min-h-screen bg-background">
	<header class="flex items-center justify-between border-b px-5 py-3">
		<div class="flex items-center gap-3"><Button variant="ghost" size="sm" onclick={() => goto(`/project/${$page.params.id}/map`)}><ArrowLeft class="mr-1 h-4 w-4" />Zpět do projektu</Button><div class="h-5 w-px bg-border"></div><div><h1 class="font-semibold">Světová mapa</h1><p class="text-xs text-muted-foreground">{document.name} · geografický pohled</p></div></div>
		<div class="flex items-center gap-2"><Button variant="outline" size="sm" onclick={() => goto(`/project/${$page.params.id}/map`)}><BookOpen class="mr-2 h-4 w-4" />Rodokmen</Button></div>
	</header>
	<main class="grid gap-4 p-4 lg:grid-cols-[220px_minmax(0,1fr)_280px]">
		<aside class="space-y-4">
			<Card><CardHeader class="pb-3"><CardTitle class="flex items-center gap-2 text-sm"><Layers3 class="h-4 w-4" />Vrstvy</CardTitle></CardHeader><CardContent><WorldLayersPanel {layers} onToggle={(layer, visible) => setWorldMapLayer(layer, visible)} /></CardContent></Card>
			<Card><CardHeader class="pb-3"><CardTitle class="flex items-center gap-2 text-sm"><MapIcon class="h-4 w-4" />Podklad</CardTitle></CardHeader><CardContent><WorldMapImportPanel onImport={(next) => updateWorldMap({ document: { name: next.name, width: next.width, height: next.height, backgroundDataUrl: next.backgroundDataUrl } })} /></CardContent></Card>
		</aside>
		<section class="min-w-0"><WorldMapCanvas {document} {points} selectedId={selected?.id ?? null} onSelect={(point) => (selected = point)} /></section>
		<aside class="space-y-4"><Card><CardHeader class="pb-3"><CardTitle class="text-sm">Inspektor</CardTitle></CardHeader><CardContent><WorldInspector {selected} /></CardContent></Card><Card class="border-dashed"><CardContent class="pt-6"><p class="text-xs leading-relaxed text-muted-foreground">Mapa je záměrně oddělená od rodokmenu. Změna polohy, vrstev nebo podkladu zde nevytváří ani nemaže jazykové vztahy.</p></CardContent></Card></aside>
	</main>
</div>
{/if}
