// Výpočty obrazovky Jazyky: proudy řeky podle mluvčích doma, karta jazyka, souhrny po stoletích.
import type { LanguagePalette, RiverStream } from '$lib/ds';
import type { ExportV2, FrameV2, GrammarSlot, Lineage } from './export';
import { speakers } from './languages';
import { villageOfGroup } from './geography';

export interface RiverFilter {
	/** index rodiny (pořadí protojazyka v zadání) nebo null = všechny */
	family: number | null;
	/** hledaný text (jméno jazyka, bez ohledu na velikost písmen a diakritiku) */
	query: string;
}

const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

/** Linie seřazené po rodinách, uvnitř rodiny podle vzniku (jak je skládá řeka). */
export function orderedLineages(lineages: Lineage[], families: Map<string, number>): Lineage[] {
	return [...lineages].sort((a, b) => (families.get(a.id) ?? 0) - (families.get(b.id) ?? 0) || a.start_year - b.start_year || a.id.localeCompare(b.id));
}

/** Proudy řeky: mluvčí doma v každém snímku, jen linie vyhovující filtru (vybraná zůstává vždy). */
export function riverStreams(
	frames: FrameV2[],
	domainOf: Map<string, string>,
	lineages: Lineage[],
	families: Map<string, number>,
	names: Map<string, string>,
	palette: LanguagePalette,
	filter: RiverFilter,
	selected: string | null = null
): { years: number[]; streams: RiverStream[] } {
	const years = frames.map((f) => f.year);
	const spoken = frames.map((f) => speakers(f.groups, domainOf));
	const q = fold(filter.query.trim());
	const streams: RiverStream[] = [];
	for (const l of orderedLineages(lineages, families)) {
		const name = names.get(l.id) ?? l.id;
		const keep = l.id === selected || ((filter.family == null || families.get(l.id) === filter.family) && (!q || fold(name).includes(q)));
		if (!keep) continue;
		const values = spoken.map((m) => m.get(l.id) ?? 0);
		if (!values.some((v) => v > 0)) continue;
		streams.push({ id: l.id, label: name, color: palette.get(l.id) ?? 'var(--ink-3)', values, end: l.end_year });
	}
	return { years, streams };
}

/** Vlastní jméno ve snímcích: jen změny, [rok, IPA]. */
export function endonymHistory(frames: FrameV2[], id: string): { year: number; ipa: string }[] {
	const out: { year: number; ipa: string }[] = [];
	let last: string | null = null;
	for (const f of frames) {
		const n = f.endonyms?.[id];
		if (n && n !== last) {
			out.push({ year: f.year, ipa: n });
			last = n;
		}
	}
	return out;
}

/** Domácí skupiny jazyka ve snímku: počet vsí a mluvčích. */
export function presence(frame: FrameV2, id: string, domainOf: Map<string, string>): { villages: number; speakers: number } {
	const vs = new Set<string>();
	let n = 0;
	for (const g of frame.groups) {
		const domain = domainOf.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
		if (domain !== 'home' || g.observed_language !== id) continue;
		vs.add(villageOfGroup(g.id));
		n += g.population;
	}
	return { villages: vs.size, speakers: n };
}

/** Průměrná retence kořenů domácích skupin linie (jen skupiny, které ji mají); null bez údaje. */
export function rootRetention(result: ExportV2, lineage: Lineage): number | null {
	const byId = new Map(result.groups.map((g) => [g.id, g]));
	const values: number[] = [];
	for (const id of new Set([...lineage.groups, ...lineage.groups_at_start])) {
		const r = byId.get(id)?.root_retention;
		if (typeof r === 'number') values.push(r);
	}
	return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

/** Největší domácí skupina linie v koncovém exportu (nese mluvnici jazyka). */
export function biggestGroup(result: ExportV2, id: string): string | null {
	let best: { id: string; population: number } | null = null;
	for (const g of result.groups) if (g.domain === 'home' && g.observed_language === id && (!best || g.population > best.population)) best = g;
	return best?.id ?? null;
}

export const GRAMMAR_FUNCTIONS = ['PAST', 'FUTURE', 'PL', 'OBJ', 'DEFINITE', 'ASPECT', 'NEG', 'ORDER'] as const;

export interface GrammarRow {
	fn: string;
	kind: string;
	/** tvar vyjádření (IPA), je-li */
	exponent: string | null;
	/** slovo, z něhož vzniklo (zdroj gramatikalizace) */
	source: string | null;
	order: string | null;
}

export function grammarRows(slots: Record<string, GrammarSlot> | undefined): GrammarRow[] {
	if (!slots) return [];
	return GRAMMAR_FUNCTIONS.filter((fn) => slots[fn]).map((fn) => ({ fn, kind: slots[fn].kind, exponent: slots[fn].exponent, source: slots[fn].source, order: slots[fn].order }));
}

/** Souhrn událostí po stoletích: řádky [století, počty druhů], jen století s aspoň jednou událostí vybraných druhů. */
export function centurySummary(summary: Record<string, Record<string, number>> | undefined, kinds: string[]): { century: number; counts: number[] }[] {
	if (!summary) return [];
	return Object.entries(summary)
		.map(([c, by]) => ({ century: Number(c), counts: kinds.map((k) => by[k] ?? 0) }))
		.filter((r) => r.counts.some((n) => n > 0))
		.sort((a, b) => a.century - b.century);
}

/** Souhrn po století → celkové součty druhů. */
export function totals(rows: { counts: number[] }[], n: number): number[] {
	return Array.from({ length: n }, (_, i) => rows.reduce((a, r) => a + r.counts[i], 0));
}
