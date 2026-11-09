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

/**
 * Malé jazyky jako variety: proud variety se přičte k proudu hostitele (vybraný jazyk zůstává sám).
 * Hostitel, kterého filtr skryl, nechá varietu samostatnou.
 */
export function mergeVarieties(river: { years: number[]; streams: RiverStream[] }, host: Map<string, string>, selected: string | null) {
	const byId = new Map(river.streams.map((s) => [s.id, { ...s, values: [...s.values] }]));
	for (const s of river.streams) {
		const h = host.get(s.id);
		if (!h || s.id === selected || !byId.has(h)) continue;
		const target = byId.get(h)!;
		s.values.forEach((v, i) => (target.values[i] += v));
		byId.delete(s.id);
	}
	return { years: river.years, streams: river.streams.filter((s) => byId.has(s.id)).map((s) => byId.get(s.id)!) };
}

// ---------------------------------------------------------------------------------------------
// Zvukové změny a analogie jazyka (`result.change_history`)

/** Značka v zápisu pravidla: hlásky (IPA), třída (C, V), hranice slova nebo soubor rysů. */
export type Sym =
	| { kind: 'ipa'; items: string[] }
	| { kind: 'class'; id: 'C' | 'V' }
	| { kind: 'edge' }
	| { kind: 'features'; spec: string };

/** Rozbor značky z exportu: `{a}`, `{i,j}`, `C`, `V`, `#`, `-son,-syl,+voi`. */
export function parseSym(s: string | null): Sym | null {
	if (!s) return null;
	if (s === '#') return { kind: 'edge' };
	if (s === 'C' || s === 'V') return { kind: 'class', id: s };
	const set = /^\{(.*)\}$/.exec(s);
	if (set) return { kind: 'ipa', items: set[1].split(',').filter(Boolean) };
	if (/^[+-]/.test(s)) return { kind: 'features', spec: s };
	return { kind: 'ipa', items: [s] };
}

/** Rysy, které umíme vysvětlit (klíč `jazyky.feat.<rys>.plus|minus`). */
export const KNOWN_FEATURES = ['voi', 'hi', 'lo', 'back', 'round', 'nas', 'cont', 'strid', 'delrel', 'son', 'syl', 'lab', 'cor', 'ant', 'distr', 'lat', 'cons', 'sg', 'x_tone'] as const;

/** Soubor rysů „+voi,-son“ → [{plus, name}]. */
export function parseFeatures(spec: string): { plus: boolean; name: string; known: boolean }[] {
	return spec
		.split(',')
		.map((x) => x.trim())
		.filter(Boolean)
		.map((x) => {
			const name = x.replace(/^[+-]/, '');
			return { plus: !x.startsWith('-'), name, known: (KNOWN_FEATURES as readonly string[]).includes(name) };
		});
}

/** Text značky pro zápis pravidla (`{i,j}`, `C`, `#`, `[+voi]`). */
export function symText(s: Sym | null): string {
	if (!s) return '';
	if (s.kind === 'ipa') return s.items.length > 1 ? `{${s.items.join(',')}}` : s.items[0];
	if (s.kind === 'class') return s.id;
	if (s.kind === 'edge') return '#';
	return `[${s.spec.replace(/-/g, '−')}]`;
}

export interface SoundRow {
	key: string;
	family: string;
	operation: string;
	target: Sym | null;
	features: string | null;
	left: Sym | null;
	right: Sym | null;
	stress: string | null;
	medial: boolean;
	/** výsledek je v exportu jen jako číslo hlásky, ne IPA */
	hiddenResult: boolean;
	year: number;
	/** vsi, kde se změna ustálila */
	villages: number;
	/** vsi, kde se proces uzavřel */
	closed: number;
	relics: number;
}

/** Záznam změn jazyka (language = id linie). */
export function languageChanges(result: ExportV2 | null, id: string | null) {
	return result?.change_history?.find((h) => h.language === id)?.changes ?? [];
}

/** Zvukové změny jazyka od nejrozšířenější (počet vsí, pak starší, pak podle klíče). */
export function soundRows(result: ExportV2 | null, id: string | null): SoundRow[] {
	const rows: SoundRow[] = [];
	languageChanges(result, id).forEach((c, i) => {
		if (c.kind !== 'sound') return;
		rows.push({
			key: `${c.variable}#${i}`,
			family: c.family,
			operation: c.operation,
			target: parseSym(c.target),
			features: typeof c.features === 'string' ? c.features : null,
			left: parseSym(c.left),
			right: parseSym(c.right),
			stress: c.stress,
			medial: c.medial === true,
			hiddenResult: c.segment != null,
			year: c.year,
			villages: c.groups.length,
			closed: c.groups.filter((g) => g.closed != null).length,
			relics: c.groups.reduce((a, g) => a + (typeof g.relics === 'number' ? g.relics : 0), 0)
		});
	});
	return rows.sort((a, b) => b.villages - a.villages || a.year - b.year || a.key.localeCompare(b.key));
}

/** Zápis pravidla: cíl → výsledek / levé _ pravé (výsledek z čísla hlásky neznáme, značí se …). */
export function ruleText(r: SoundRow): string {
	const target = symText(r.target);
	const ctx = r.left || r.right ? ` / ${symText(r.left)}_${symText(r.right)}` : '';
	const result = r.features ? symText({ kind: 'features', spec: r.features }) : '…';
	switch (r.operation) {
		case 'delete':
			return `${target} → ∅${ctx}`;
		case 'insert_before':
			return `∅ → ${result} / ${symText(r.left)}_${target}`;
		case 'merge_next':
			return `${target}+ → ${result}${ctx}`;
		default:
			return `${target} → ${result}${ctx}`;
	}
}

export interface AnalogyRow {
	key: string;
	operation: string;
	concept: string | null;
	cell: string | null;
	year: number;
	villages: number;
}

export function analogyRows(result: ExportV2 | null, id: string | null): AnalogyRow[] {
	const rows: AnalogyRow[] = [];
	languageChanges(result, id).forEach((c, i) => {
		if (c.kind !== 'analogy') return;
		rows.push({ key: `${c.variable}#${i}`, operation: c.operation, concept: c.concept, cell: c.cell, year: c.year, villages: c.groups.length });
	});
	return rows.sort((a, b) => b.villages - a.villages || a.year - b.year || a.key.localeCompare(b.key));
}

/** Počet analogií podle operace, od nejčastější. */
export function analogyCounts(rows: AnalogyRow[]): { operation: string; count: number }[] {
	const m = new Map<string, number>();
	for (const r of rows) m.set(r.operation, (m.get(r.operation) ?? 0) + 1);
	return [...m].map(([operation, count]) => ({ operation, count })).sort((a, b) => b.count - a.count || a.operation.localeCompare(b.operation));
}

/** Buňky mluvnice z analogií (PL, OBJ, PAST, FUT, DEF) → funkce `jazyky.fn.*`. */
export const CELL_FUNCTION: Record<string, string> = { PL: 'PL', OBJ: 'OBJ', PAST: 'PAST', FUT: 'FUTURE', DEF: 'DEFINITE' };
