// Výpočty obrazovky Atlas nad snímkem roku.
import type { MapLabel, MapVillage } from '$lib/ds';
import type { FrameV2 } from './export';
import { villageOfGroup } from './geography';

/** Popisky jazyků: těžiště jejich vsí, jen u jazyků s aspoň `min` vesmi; největší první. */
export function languageLabels(home: Map<string, { lineage: string }>, names: (id: string) => string, min = 4): MapLabel[] {
	const byLineage = new Map<string, string[]>();
	for (const [village, h] of home) {
		if (!byLineage.has(h.lineage)) byLineage.set(h.lineage, []);
		byLineage.get(h.lineage)!.push(village);
	}
	return [...byLineage.entries()]
		.filter(([, vs]) => vs.length >= min)
		.sort((a, b) => b[1].length - a[1].length)
		.map(([id, vs]) => ({ text: names(id), villages: vs, kind: 'language' as const }));
}

/** Skupiny kraje ve snímku: ves → [{jazyk, lidí}] (jen domácí skupiny), od největší. */
export function regionGroups(frame: FrameV2, villages: MapVillage[], region: string, domainOf: Map<string, string>) {
	const inRegion = new Set(villages.filter((v) => v.region === region).map((v) => v.id));
	const out = new Map<string, { lineage: string | null; population: number; group: string }[]>();
	for (const g of frame.groups) {
		const v = villageOfGroup(g.id);
		if (!inRegion.has(v)) continue;
		const domain = domainOf.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
		if (domain !== 'home') continue;
		if (!out.has(v)) out.set(v, []);
		out.get(v)!.push({ lineage: g.observed_language, population: g.population, group: g.id });
	}
	for (const list of out.values()) list.sort((a, b) => b.population - a.population);
	return out;
}
