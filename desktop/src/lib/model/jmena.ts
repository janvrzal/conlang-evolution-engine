// Jména s historií (modul jmen enginu, dok. 34): generátor jmen sídel a osob podle kraje
// a epochy (příkaz run_names / POST /api/v2/runs/{id}/names) a historie jmen z exportu (`names`).

/** Dotaz na generátor (`names::generate::Query` v enginu). */
export interface NamesQuery {
	region: string;
	year: number;
	count?: number;
	/** do kterého roku jméno vést; bez něj do posledního pozorování */
	until?: number | null;
	/** město (jinak vesnice); jen u sídel */
	urban?: boolean;
	/** jiný pokus = jiné návrhy, stejný pokus vždy stejné */
	attempt?: number;
	kind?: 'place' | 'person';
}

/** Podoba jména v čase. `cause`: `founded`, `inherited`, `borrowed`, `sound: …`, `borrowed: a → b`. */
export interface NameStep {
	year: number;
	ipa: string;
	name: string;
	cause: string;
	language?: string;
}

export interface RecipePart {
	[key: string]: unknown;
}

export interface PlaceSuggestion {
	/** dnešní tvar (v roce `until`) */
	name: string;
	ipa: string;
	language: string;
	lineage: string;
	founded: {
		year: number;
		name: string;
		ipa: string;
		language: string;
		lineage: string;
		tradition: string;
		pattern: string;
		meaning: string;
		recipe: RecipePart[];
		/** rok pozorování, ze kterého jsou slova */
		words_from: number;
	};
	timeline: NameStep[];
}

export interface PlaceNames {
	region: string;
	year: number;
	until: number;
	urban: boolean;
	tradition: string;
	names: PlaceSuggestion[];
}

export interface PersonSuggestion {
	name: string;
	ipa: string;
	given: string;
	house: string | null;
	paradigm: string;
	meaning: string;
	recipe: RecipePart[];
}

export interface PersonNames {
	region: string;
	year: number;
	kind: 'person';
	language: string;
	lineage: string;
	tradition: string;
	tradition_label: string | null;
	tradition_since: number | null;
	tradition_cause: string | null;
	tradition_source: string | null;
	words_from: number;
	names: PersonSuggestion[];
}

export type NamesResult = PlaceNames | PersonNames;

export const isPersons = (r: NamesResult): r is PersonNames => (r as PersonNames).kind === 'person';

/** Záznam jména v exportu (`names.records`). */
export interface NameRecord {
	id: string;
	/** `language:<id>`, `lineage:<id>`, `territory:<id>`, `state:<id>`, `person:…`, `world` */
	object: string;
	role: 'endonym' | 'exonym';
	name: string;
	ipa: string;
	language: string;
	lineage: string | null;
	founded: number;
	ended: number | null;
	full_name: string | null;
	motivation: string;
	cause: string | null;
	tradition: string | null;
	meaning: string;
	recipe: RecipePart[];
	source: { record: string; ipa: string; language: string } | null;
	timeline: NameStep[];
}

export interface NamesExport {
	records: NameRecord[];
	traditions?: unknown;
	objects: Record<string, { endonym: string | null; records: string[]; exonyms: Record<string, string> }>;
}

/** Příčina změny tvaru rozložená pro popisek: druh a podrobnost (pravidlo, jazyky). */
export function stepCause(cause: string): { kind: 'founded' | 'inherited' | 'borrowed' | 'sound' | 'other'; detail: string } {
	const [head, ...rest] = cause.split(':');
	const detail = rest.join(':').trim();
	if (head === 'sound') return { kind: 'sound', detail };
	if (head === 'founded' || head === 'inherited' || head === 'borrowed') return { kind: head, detail };
	return { kind: 'other', detail: cause };
}

/** Klíč popisku příčiny (`jmena.cause.*`) a dosazované hodnoty; neznámá příčina zůstane textem. */
export function causeMessage(cause: string): { key: string; params: Record<string, string> } | { text: string } {
	const c = stepCause(cause);
	if (c.kind === 'other') return { text: c.detail };
	if (c.kind === 'sound') return { key: 'jmena.cause.sound', params: { detail: c.detail } };
	if (c.kind === 'borrowed' && c.detail) return { key: 'jmena.cause.borrowed_from', params: { detail: c.detail } };
	return { key: `jmena.cause.${c.kind}`, params: {} };
}

/** Počet hláskových změn na časové ose jména. */
export const soundChanges = (timeline: NameStep[]) => timeline.filter((s) => s.cause.startsWith('sound')).length;

/**
 * Epochy generátoru: roky pozorování běhu (snímků), od kterých jsou dobová slova.
 * Rok mezi pozorováními bere slova z posledního předchozího pozorování.
 */
export function epochOf(years: number[], year: number): number | null {
	let found: number | null = null;
	for (const y of years) if (y <= year + 1e-9) found = y;
	return found ?? years[0] ?? null;
}

/** Klíč objektu linie v `names.objects`; id linie z exportu už předponu `lineage:` nese. */
export const lineageObject = (id: string) => (id.startsWith('lineage:') ? id : `lineage:${id}`);

/** Historie jména objektu z exportu: současné endonymum, dřívější endonyma a exonyma podle linií. */
export interface NameHistory {
	current: NameRecord | null;
	/** dřívější endonyma (ukončená), od nejstaršího */
	earlier: NameRecord[];
	/** jak objekt jmenují jiné linie (linie → záznam) */
	exonyms: { lineage: string; record: NameRecord }[];
}

export function nameHistory(names: NamesExport | null | undefined, object: string): NameHistory | null {
	const entry = names?.objects?.[object];
	if (!names || !entry) return null;
	const byId = new Map(names.records.map((r) => [r.id, r]));
	const current = entry.endonym ? (byId.get(entry.endonym) ?? null) : null;
	const earlier = entry.records
		.map((id) => byId.get(id))
		.filter((r): r is NameRecord => !!r && r.role === 'endonym' && r.id !== current?.id)
		.sort((a, b) => a.founded - b.founded);
	const exonyms = Object.entries(entry.exonyms)
		.map(([lineage, id]) => ({ lineage, record: byId.get(id) }))
		.filter((e): e is { lineage: string; record: NameRecord } => !!e.record)
		.sort((a, b) => a.lineage.localeCompare(b.lineage));
	return { current, earlier, exonyms };
}

/** Text, který jde zkopírovat: jedno jméno na řádek (dnešní tvar ← tvar při založení, význam). */
export function namesAsText(result: NamesResult): string {
	if (isPersons(result)) return result.names.map((n) => (n.meaning ? `${n.name} (${n.meaning})` : n.name)).join('\n');
	return result.names.map((n) => `${n.name} ← ${n.founded.name} (${n.founded.meaning})`).join('\n');
}
