// Výpočty obrazovky Co kdyby: porovnání dvou běhů (A hlavní, B větev) nad snímkem roku.
import type { WorldSpec } from '$lib/state.svelte';
import type { ExportV2, FrameV2 } from './export';
import { villageOfGroup } from './geography';
import { homeLanguage, lineageFamilies } from './languages';

export type Home = Map<string, { lineage: string; population: number; group: string }>;

/** Jazyk větve B je „tentýž“ jako jazyk A, když s ním sdílí aspoň polovinu svých vsí a patří do stejné rodiny (do větvení jsou běhy shodné). */
export function matchLineages(homeA: Home, homeB: Home, families?: { a: Map<string, number>; b: Map<string, number> }): Map<string, string | null> {
	const counts = new Map<string, Map<string, number>>();
	const total = new Map<string, number>();
	for (const [village, b] of homeB) {
		total.set(b.lineage, (total.get(b.lineage) ?? 0) + 1);
		if (!counts.has(b.lineage)) counts.set(b.lineage, new Map());
		const a = homeA.get(village);
		if (a) counts.get(b.lineage)!.set(a.lineage, (counts.get(b.lineage)!.get(a.lineage) ?? 0) + 1);
	}
	const out = new Map<string, string | null>();
	for (const [lin, c] of counts) {
		const best = [...c.entries()].sort((x, y) => y[1] - x[1])[0];
		// jazyk z jiné rodiny není „tentýž“, ani když sdílí většinu vsí (přechod na cizí jazyk)
		const sameFamily = !families || families.a.get(best?.[0] ?? '') === families.b.get(lin);
		out.set(lin, best && sameFamily && best[1] * 2 >= (total.get(lin) ?? 1) ? best[0] : null);
	}
	return out;
}

/** Vsi, kde se doma mluví jiným jazykem (po spárování jazyků B s A). */
export function differingVillages(homeA: Home, homeB: Home, match: Map<string, string | null>): Set<string> {
	const out = new Set<string>();
	for (const [v, a] of homeA) {
		const b = homeB.get(v);
		if (b && a.lineage !== match.get(b.lineage)) out.add(v);
	}
	return out;
}

/** Kraje s rozdílem (`core`) a kraje kolem nich (`all`): rámování přiblížení. */
export function focusRegions(diff: Set<string>, regionOf: Map<string, string>, neighbours: (region: string) => string[]) {
	const core = new Set<string>();
	for (const v of diff) {
		const r = regionOf.get(v);
		if (r) core.add(r);
	}
	const all = new Set(core);
	for (const r of core) for (const n of neighbours(r)) all.add(n);
	return { core, all };
}

type Ev = WorldSpec['events'][number];
const key = (e: Ev) => JSON.stringify(e);

/** Události, kterými se zadání větví liší: jen v A (v B vynechané) a jen v B (přidané). */
export function worldDifference(a: WorldSpec, b: WorldSpec) {
	const kb = new Set(b.events.map(key)), ka = new Set(a.events.map(key));
	const onlyA = a.events.filter((e) => !kb.has(key(e)));
	const onlyB = b.events.filter((e) => !ka.has(key(e)));
	const year = Math.min(...[...onlyA, ...onlyB].map((e) => e.year));
	return { onlyA, onlyB, year: Number.isFinite(year) ? year : null };
}

/** Kopie zadání bez události s daným indexem (základ nové větve). */
export function withoutEvent(world: WorldSpec, index: number): WorldSpec {
	const copy = JSON.parse(JSON.stringify(world)) as WorldSpec;
	copy.events.splice(index, 1);
	return copy;
}

/** Mluvčí doma podle rodiny (index protojazyka v zadání). */
export function familySpeakers(frame: FrameV2, domainOf: Map<string, string>, families: Map<string, number>): Map<number, number> {
	const out = new Map<number, number>();
	for (const g of frame.groups) {
		const domain = domainOf.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
		if (domain !== 'home' || !g.observed_language) continue;
		const f = families.get(g.observed_language) ?? 0;
		out.set(f, (out.get(f) ?? 0) + g.population);
	}
	return out;
}

/** Počet vsí, kde se rodina jazyka doma v A a B liší. */
export function differingFamilies(homeA: Home, homeB: Home, famA: Map<string, number>, famB: Map<string, number>): number {
	let n = 0;
	for (const [v, a] of homeA) {
		const b = homeB.get(v);
		if (b && (famA.get(a.lineage) ?? 0) !== (famB.get(b.lineage) ?? 0)) n++;
	}
	return n;
}

export interface Side {
	world: WorldSpec;
	result: ExportV2;
	frames: FrameV2[];
}

export const domainsOf = (result: ExportV2) => new Map(result.groups.map((g) => [g.id, g.domain]));
export const sideHome = (frame: FrameV2, result: ExportV2): Home => homeLanguage(frame.groups, domainsOf(result));
export const sideFamilies = (s: Side) => lineageFamilies(s.world, s.result);

/** Největší domácí skupina kraje ve snímku (její slovník reprezentuje slova kraje). */
export function regionGroup(frame: FrameV2, result: ExportV2, villages: { id: string; region: string }[], region: string): string | null {
	const inRegion = new Set(villages.filter((v) => v.region === region).map((v) => v.id));
	const domainOf = domainsOf(result);
	let best: { id: string; population: number } | null = null;
	for (const g of frame.groups) {
		if (!inRegion.has(villageOfGroup(g.id))) continue;
		if ((domainOf.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home')) !== 'home') continue;
		if (!best || g.population > best.population) best = { id: g.id, population: g.population };
	}
	return best?.id ?? null;
}

/** Slova dvou skupin: tvary v A a B u vybraných pojmů; `changed` z `total` společných pojmů se liší. */
export function compareWords(a: ExportV2, ga: string | null, b: ExportV2, gb: string | null, concepts: string[]) {
	const la = ga ? a.lexicon[ga] : undefined, lb = gb ? b.lexicon[gb] : undefined;
	if (!la || !lb) return null;
	const shared = Object.keys(la).filter((c) => lb[c]);
	const changed = shared.filter((c) => la[c].form !== lb[c].form).length;
	const rows = concepts.filter((c) => la[c] && lb[c]).map((c) => ({ concept: c, a: la[c].form, b: lb[c].form, differs: la[c].form !== lb[c].form }));
	return { rows, changed, total: shared.length };
}
