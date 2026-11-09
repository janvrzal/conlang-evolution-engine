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
