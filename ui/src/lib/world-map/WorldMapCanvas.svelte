<script lang="ts">
	import { LocateFixed, ZoomIn, ZoomOut } from 'lucide-svelte';
	import { onMount } from 'svelte';
	import type { Map as OlMap } from 'ol';
	import type { WorldMapDocument, WorldMapPoint } from './types';
	import type { WorldLayerId, WorldRegion, WorldRoute, WorldSettlement, PoliticalEntity, MapGeometry } from '$lib/world-model';
	import { pointToPixels, visibleWorldPoints } from './renderer';

	let {
		document = null,
		points = [],
		regions = [],
		settlements = [],
		routes = [],
		politicalEntities = [],
		layers = { languages: true, regions: true, settlements: true, routes: false, politics: false },
		selectedId = null,
		onSelect
	}: {
		document?: WorldMapDocument | null;
		points?: WorldMapPoint[];
		regions?: WorldRegion[];
		settlements?: WorldSettlement[];
		routes?: WorldRoute[];
		politicalEntities?: PoliticalEntity[];
		layers?: Record<WorldLayerId, boolean>;
		selectedId?: string | null;
		onSelect?: (point: WorldMapPoint) => void;
	} = $props();

	let mapHost: HTMLDivElement;
	let map: OlMap | null = null;
	let mounted = false;
	let renderVersion = 0;

	function normalizedPoint(point: { x: number; y: number }, document: WorldMapDocument): [number, number] {
		const [x, y] = pointToPixels({ id: '', label: '', ...point }, document);
		return [x, document.height - y];
	}

	function geometryCoordinates(geometry: MapGeometry | null, document: WorldMapDocument): unknown {
		if (!geometry) return null;
		if (geometry.kind === 'point') return normalizedPoint(geometry, document);
		return geometry.points.map((point) => normalizedPoint(point, document));
	}

	async function render() {
		if (!mounted || !mapHost || !document) return;
		const version = ++renderVersion;
		const [{ default: OlMapClass }, { default: View }, { default: Projection }, { default: Feature }, { default: Point }, { default: LineString }, { default: Polygon }, { default: VectorSource }, { default: VectorLayer }, { default: ImageLayer }, { default: Static }, { default: Style }, { default: CircleStyle }, { default: Fill }, { default: Stroke }] = await Promise.all([
			import('ol/Map'), import('ol/View'), import('ol/proj/Projection'), import('ol/Feature'), import('ol/geom/Point'), import('ol/geom/LineString'), import('ol/geom/Polygon'), import('ol/source/Vector'), import('ol/layer/Vector'), import('ol/layer/Image'), import('ol/source/ImageStatic'), import('ol/style/Style'), import('ol/style/Circle'), import('ol/style/Fill'), import('ol/style/Stroke')
		]);
		if (version !== renderVersion) return;
		map?.setTarget(undefined);
		map = null;
		mapHost.replaceChildren();
		const extent: [number, number, number, number] = [0, 0, document.width, document.height];
		const projection = new Projection({ code: `CEE:${document.name}`, units: 'pixels', extent });
		const layersForMap: any[] = [];
		const background = document.backgroundDataUrl ?? document.backgroundUrl;
		if (background) {
			layersForMap.push(new ImageLayer({ source: new Static({ url: background, projection, imageExtent: extent, crossOrigin: 'anonymous' }), opacity: 0.72 }));
		}
		const source = new VectorSource();
		const featureById = new Map<string, WorldMapPoint>();
		const pointStyle = new Style({ image: new CircleStyle({ radius: 6, fill: new Fill({ color: '#fbbf24' }), stroke: new Stroke({ color: '#111827', width: 2 }) }) });
		for (const point of layers.languages ? visibleWorldPoints(points, 1) : []) {
			const feature = new Feature({ geometry: new Point(normalizedPoint(point, document)), worldPointId: point.id });
			feature.setStyle(pointStyle);
			source.addFeature(feature);
			featureById.set(point.id, point);
		}
		const addGeometry = (id: string, geometry: MapGeometry | null, kind: 'line' | 'polygon') => {
			const coordinates = geometryCoordinates(geometry, document);
			if (!coordinates) return;
			const shape = kind === 'line' ? new LineString(coordinates as [number, number][]) : new Polygon([coordinates as [number, number][]]);
			const feature = new Feature({ geometry: shape, worldPointId: id });
			feature.setStyle(new Style({ fill: new Fill({ color: kind === 'polygon' ? 'rgba(59,130,246,.12)' : 'transparent' }), stroke: new Stroke({ color: kind === 'polygon' ? '#60a5fa' : '#34d399', width: 2 }) }));
			source.addFeature(feature);
		};
		for (const region of regions) if (layers.regions) {
			addGeometry(region.id, region.geometry, 'polygon');
			if (region.geometry?.kind === 'point') featureById.set(region.id, { id: region.id, label: region.label, x: region.geometry.x, y: region.geometry.y, kind: 'region' });
		}
		for (const route of routes) if (layers.routes) addGeometry(route.id, route.geometry, 'line');
		for (const entity of politicalEntities) if (layers.politics) addGeometry(entity.id, entity.geometry, 'polygon');
		for (const settlement of settlements) if (layers.settlements) {
			const point = { id: settlement.id, label: settlement.label, x: settlement.geometry.x, y: settlement.geometry.y, kind: 'settlement' as const };
			const feature = new Feature({ geometry: new Point(normalizedPoint(point, document)), worldPointId: point.id });
			feature.setStyle(new Style({ image: new CircleStyle({ radius: 4, fill: new Fill({ color: '#f8fafc' }), stroke: new Stroke({ color: '#64748b', width: 1.5 }) }) }));
			source.addFeature(feature); featureById.set(point.id, point);
		}
		layersForMap.push(new VectorLayer({ source }));
		map = new OlMapClass({ target: mapHost, layers: layersForMap, view: new View({ projection, extent, center: [document.width / 2, document.height / 2], zoom: 1, minZoom: -3, maxZoom: 8 }) });
		map.getView().fit(extent, { padding: [12, 12, 12, 12], duration: 0 });
		map.on('singleclick', (event) => {
			const feature = map?.forEachFeatureAtPixel(event.pixel, (candidate) => candidate);
			const id = feature?.get('worldPointId');
			const selected = id ? featureById.get(id) : undefined;
			if (selected) onSelect?.(selected);
		});
	}

	onMount(() => {
		mounted = true;
		render();
		return () => { renderVersion++; map?.setTarget(undefined); map = null; };
	});

	$effect(() => {
		document?.name; document?.backgroundDataUrl; points.length; regions.length; settlements.length; routes.length; politicalEntities.length; Object.values(layers).join(',');
		if (mounted) render();
	});

	function changeZoom(delta: number) { const view = map?.getView(); if (view) view.setZoom(Math.max(-3, Math.min(8, (view.getZoom() ?? 1) + delta))); }
	function resetView() { if (map && document) map.getView().fit([0, 0, document.width, document.height], { padding: [12, 12, 12, 12], duration: 300 }); }
</script>

<section class="relative min-h-[560px] overflow-hidden rounded-xl border bg-slate-950 text-white" aria-label="World map canvas">
	<div bind:this={mapHost} class="absolute inset-0"></div>
	<div class="absolute bottom-4 left-4 z-10 flex items-center gap-1 rounded-lg border border-white/15 bg-black/55 p-1 backdrop-blur">
		<button class="rounded p-2 hover:bg-white/10" title="Přiblížit" aria-label="Přiblížit" onclick={() => changeZoom(.5)}><ZoomIn class="h-4 w-4" /></button>
		<button class="rounded p-2 hover:bg-white/10" title="Oddálit" aria-label="Oddálit" onclick={() => changeZoom(-.5)}><ZoomOut class="h-4 w-4" /></button>
		<button class="rounded p-2 hover:bg-white/10" title="Výchozí pohled" aria-label="Výchozí pohled" onclick={resetView}><LocateFixed class="h-4 w-4" /></button>
	</div>
	<div class="absolute right-4 top-4 z-10 rounded-md border border-white/15 bg-black/55 px-3 py-2 text-xs text-white/70 backdrop-blur">OpenLayers · geografický pohled</div>
	{#if points.length === 0 && regions.length === 0 && settlements.length === 0}<p class="absolute inset-0 z-10 flex items-center justify-center text-sm text-white/60">Zatím nejsou rozmístěny žádné geografické body.</p>{/if}
</section>

<style>
	:global(.ol-viewport) { border-radius: inherit; }
	:global(.ol-control button) { background: rgba(15, 23, 42, .75); color: white; }
</style>
