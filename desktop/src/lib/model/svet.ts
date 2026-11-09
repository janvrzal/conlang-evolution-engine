// Výpočty obrazovky Svět: upozornění z kalibrace enginu a pomocné údaje o krajích.
import type { WorldSpec } from '$lib/state.svelte';

type Region = WorldSpec['regions'][number];

/** Má kraj město? (city 0 nebo chybějící hodnota = bez města) */
export const hasCity = (r: Pick<Region, 'city'>) => (r.city ?? 0) > 0;

/** Kraje bez města: malý kraj se slabými vazbami se bez města rozpadá na jazyk za vesnici. */
export function regionsWithoutCity(world: WorldSpec): string[] {
	return world.regions.filter((r) => !hasCity(r)).map((r) => r.id);
}

/**
 * Kraje s jediným jazykem: všichni sousedé mluví týmž jazykem jako kraj samotný, takže uvnitř
 * nevznikne nářeční hranice; větve přijdou jen přes hranice států nebo osídlení.
 */
export function singleLanguageRegions(world: WorldSpec): string[] {
	const lang = new Map(world.regions.map((r) => [r.id, r.language ?? null]));
	return world.regions
		.filter((r) => {
			const mine = lang.get(r.id);
			const near = (r.neighbours ?? []).filter((n) => lang.has(n));
			return mine != null && near.length > 0 && near.every((n) => lang.get(n) === mine);
		})
		.map((r) => r.id);
}

export interface WorldWarning {
	kind: 'no_city' | 'single_language';
	regions: string[];
}

export function worldWarnings(world: WorldSpec): WorldWarning[] {
	const out: WorldWarning[] = [];
	const noCity = regionsWithoutCity(world);
	if (noCity.length) out.push({ kind: 'no_city', regions: noCity });
	const single = singleLanguageRegions(world);
	if (single.length) out.push({ kind: 'single_language', regions: single });
	return out;
}

/** Počet krajů podle jazyka na počátku (index jazyka v zadání → počet). */
export function regionsPerLanguage(world: WorldSpec): Map<string, number> {
	const out = new Map<string, number>();
	for (const r of world.regions) if (r.language) out.set(r.language, (out.get(r.language) ?? 0) + 1);
	return out;
}

/** Možnosti velikosti města; aktuální hodnota mimo nabídku se přidá, aby se nezměnila potichu. */
export function cityOptions(current: number | null | undefined): number[] {
	const base = [0, 2, 3, 4, 6];
	const c = current ?? 0;
	return base.includes(c) ? base : [...base, c].sort((a, b) => a - b);
}

/** Úrovně ze schématu v pořadí `order`; chybějící ve schématu se vynechají, bez schématu platí `order`. */
export function levelsInOrder(schemaLevels: string[] | undefined, order: string[]): string[] {
	if (!schemaLevels) return order;
	const known = order.filter((l) => schemaLevels.includes(l));
	return [...known, ...schemaLevels.filter((l) => !order.includes(l))];
}

// ---------- úpravy krajů na mapě ----------
type Spec = import('$lib/state.svelte').WorldSpec;

/** Nové jedinečné ID kraje (r1, r2, …). */
export function nextRegionId(world: Spec): string {
	const used = new Set(world.regions.map((r) => r.id));
	let n = world.regions.length + 1;
	while (used.has(`r${n}`)) n++;
	return `r${n}`;
}

/** Nejbližší kraje k bodu (pro napojení nového kraje). */
export function nearestRegions(world: Spec, x: number, y: number, count: number, except?: string): string[] {
	return world.regions
		.filter((r) => r.id !== except)
		.map((r) => ({ id: r.id, d: Math.hypot(r.position[0] - x, r.position[1] - y) }))
		.sort((a, b) => a.d - b.d)
		.slice(0, count)
		.map((r) => r.id);
}

/** Přidá kraj na místo (x, y) napojený na `link` nejbližších krajů; vrátí jeho ID. Jazyk a krajina podle nejbližšího. */
export function addRegion(world: Spec, x: number, y: number, name: string, link = 2): string {
	const id = nextRegionId(world);
	const near = nearestRegions(world, x, y, link);
	const closest = world.regions.find((r) => r.id === near[0]);
	world.regions.push({ id, name, position: [round(x), round(y)], neighbours: near, language: closest?.language, terrain: closest?.terrain ?? 'plain' });
	for (const n of near) {
		const r = world.regions.find((q) => q.id === n);
		if (r && !(r.neighbours ?? []).includes(id)) r.neighbours = [...(r.neighbours ?? []), id];
	}
	return id;
}

/** Přepne sousedství dvou krajů (oběma směry). Vrátí true, když jsou teď sousedé. */
export function toggleNeighbours(world: Spec, a: string, b: string): boolean {
	const ra = world.regions.find((r) => r.id === a), rb = world.regions.find((r) => r.id === b);
	if (!ra || !rb || a === b) return false;
	const linked = (ra.neighbours ?? []).includes(b) || (rb.neighbours ?? []).includes(a);
	if (linked) {
		ra.neighbours = (ra.neighbours ?? []).filter((n) => n !== b);
		rb.neighbours = (rb.neighbours ?? []).filter((n) => n !== a);
	} else {
		ra.neighbours = [...(ra.neighbours ?? []), b];
		rb.neighbours = [...(rb.neighbours ?? []), a];
	}
	return !linked;
}

/** Smaže kraj i jeho vazby k sousedům. Události, které na kraj odkazují, ohlásí ověření zadání. */
export function removeRegion(world: Spec, id: string) {
	world.regions = world.regions.filter((r) => r.id !== id);
	for (const r of world.regions) if (r.neighbours?.includes(id)) r.neighbours = r.neighbours.filter((n) => n !== id);
}

/** Kolik událostí zadání odkazuje na kraj (pro upozornění před smazáním). */
export function eventsUsingRegion(world: Spec, id: string): number {
	return world.events.filter((e) => JSON.stringify(e).includes(`"${id}"`)).length;
}

const round = (v: number) => Math.round(v * 10) / 10;
