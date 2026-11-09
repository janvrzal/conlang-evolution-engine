// Mapa světa pro <WorldMap>: kraje ze zadání, vsi z exportu (úroveň settlement).
// Před během vsi nejsou známé; pak má každý kraj jednu „ves“ na své poloze.
import type { MapMarker, MapRegion, MapVillage } from '$lib/ds';
import type { WorldSpec } from '$lib/state.svelte';
import type { ExportV2 } from './export';

export interface WorldGeography {
	regions: MapRegion[];
	villages: MapVillage[];
	/** ves → kraj */
	regionOf: Map<string, string>;
	/** jméno kraje nebo vsi (z onomastiky enginu, jinak ze zadání) */
	name: (id: string) => string;
}

export function geography(world: WorldSpec, result: ExportV2 | null): WorldGeography {
	const toponyms = result?.onomastics?.toponyms ?? {};
	const territory = new Map((result?.territories ?? []).map((t) => [t.id, t]));
	const name = (id: string) => {
		const spec = world.regions.find((r) => r.id === id)?.name;
		// generované jméno „kraj · 3“ nahradí jméno z onomastiky enginu
		if (spec && !spec.includes('·')) return spec;
		return toponyms[id]?.name ?? territory.get(id)?.name ?? spec ?? id;
	};
	const regions: MapRegion[] = world.regions.map((r) => ({
		id: r.id,
		name: name(r.id),
		position: [r.position[0], r.position[1]],
		terrain: r.terrain ?? null,
		neighbours: [...(r.neighbours ?? [])]
	}));
	const settlements = (result?.territories ?? []).filter((t) => t.level === 'settlement' && t.position && t.parent);
	const villages: MapVillage[] = settlements.length
		? settlements.map((t) => ({ id: t.id, region: t.parent!, x: t.position![0], y: t.position![1] }))
		: regions.map((r) => ({ id: r.id, region: r.id, x: r.position[0], y: r.position[1] }));
	return { regions, villages, regionOf: new Map(villages.map((v) => [v.id, v.region])), name };
}

/** Města (sídla s městským jménem) jako čtverečky na mapě. */
export function cityMarkers(result: ExportV2 | null): MapMarker[] {
	if (!result) return [];
	return result.territories.filter((t) => t.level === 'settlement' && t.toponym?.urban).map((t) => ({ village: t.id, kind: 'city' as const }));
}

/** Ves skupiny: id skupiny je „ves“ nebo „ves>jazyk“ (druhá skupina ve vsi). */
export const villageOfGroup = (groupId: string) => groupId.split('>')[0];
