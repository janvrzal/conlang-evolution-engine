/** Read-only world-map contract. Geography is intentionally separate from genealogy. */
import type { WorldLayerId, WorldMapPoint } from '$lib/world-model';
export type { WorldLayerId, WorldMapPoint } from '$lib/world-model';

export type WorldMapDocument = {
	name: string;	width: number;	height: number;
	/** Legacy renderer alias; persisted imports use backgroundDataUrl. */
	backgroundUrl?: string;
	backgroundDataUrl?: string;
};

export type WorldMapAdapter = {
	/** Render only the geographic surface. It must not create or mutate genealogy. */
	mount: (element: HTMLElement, document: WorldMapDocument) => void;
	destroy?: () => void;
};

export const defaultWorldMapDocument: WorldMapDocument = {
	name: 'Prázdný svět', width: 2400, height: 1400
};

export const defaultWorldMapPoints: WorldMapPoint[] = [
	{ id: 'north-coast', label: 'Severní pobřeží', x: 24, y: 29, family: 'Asterická', languageId: 'asteric-coast', kind: 'language' },
	{ id: 'river-delta', label: 'Říční delta', x: 62, y: 52, family: 'Belarická', languageId: 'belaric-delta', kind: 'language' },
	{ id: 'island-west', label: 'Západní ostrovy', x: 80, y: 27, family: 'Norická', languageId: 'noric-west', kind: 'language' }
];
