import type { WorldMapDocument, WorldMapPoint } from './types';

/**
 * Coordinate helpers shared by map renderers.  The editor uses a deliberately
 * projection-agnostic, top-left origin coordinate space: imported pixels are
 * (0..document.width, 0..document.height), while the UI contract accepts
 * normalized percentages for painless authoring and legacy migration.
 */
export function pointToPixels(point: WorldMapPoint, document: WorldMapDocument): [number, number] {
	const x = point.x <= 1 ? point.x * document.width : (point.x / 100) * document.width;
	const y = point.y <= 1 ? point.y * document.height : (point.y / 100) * document.height;
	return [x, y];
}

export function pointToPercent(point: WorldMapPoint): [number, number] {
	return [point.x <= 1 ? point.x * 100 : point.x, point.y <= 1 ? point.y * 100 : point.y];
}

/** Stable LOD policy: dense language points are hidden while zoomed out. */
export function visibleWorldPoints(points: WorldMapPoint[], zoom: number): WorldMapPoint[] {
	if (zoom >= 1.25 || points.length <= 250) return points;
	const stride = zoom < 0.8 ? 4 : zoom < 1 ? 2 : 1;
	if (stride === 1) return points;
	return points.filter((point, index) => point.kind === 'region' || index % stride === 0);
}

/** A renderer-neutral style hint; OpenLayers and the SVG fallback can share it. */
export function pointRadius(point: WorldMapPoint, zoom: number): number {
	const base = point.kind === 'region' ? 9 : point.kind === 'settlement' ? 5 : 6;
	return Math.max(3, Math.min(14, base / Math.sqrt(Math.max(zoom, 0.4))));
}
