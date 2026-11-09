// Výpočty obrazovky Slova: tvary jednoho pojmu ve vsích, izoglosy a vrt kraje (jen z koncového exportu).
import type { ExportV2, LexEntry } from './export';
import { conceptLabel } from './concepts';
import type { Locale } from '$lib/i18n.svelte';

/** Pojmy slovníku výsledku (sjednocení přes skupiny), seřazené podle popisku. */
export function conceptList(result: ExportV2, locale: Locale): { value: string; label: string }[] {
	const ids = new Set<string>();
	for (const lex of Object.values(result.lexicon)) for (const c of Object.keys(lex)) ids.add(c);
	return [...ids]
		.map((value) => ({ value, label: conceptLabel(value, locale) }))
		.sort((a, b) => a.label.localeCompare(b.label, locale));
}

export interface VillageForm {
	form: string;
	group: string;
	lineage: string;
	/** záznam z koncového exportu; v průběžném roce (slovník z pozorování) není */
	entry: LexEntry | null;
	/** slovo má kořen v jiné rodině, než je rodina skupiny (výpůjčka nebo cizí původ) */
	foreign: boolean;
}

/** Ves → tvar pojmu v největší domácí skupině vsi. */
export function villageForms(
	result: ExportV2,
	home: Map<string, { lineage: string; group: string }>,
	concept: string
): Map<string, VillageForm> {
	const code = new Map(result.groups.map((g) => [g.id, g.code_language]));
	const out = new Map<string, VillageForm>();
	for (const [village, h] of home) {
		const entry = result.lexicon[h.group]?.[concept];
		if (!entry) continue;
		out.set(village, {
			form: entry.form,
			group: h.group,
			lineage: h.lineage,
			entry,
			foreign: entry.loan || (!!code.get(h.group) && entry.language !== code.get(h.group))
		});
	}
	return out;
}

export interface FormArea {
	form: string;
	villages: number;
	foreign: boolean;
}

/** Různé tvary a počet vsí, kde se říkají; nejčastější první. */
export function formAreas(forms: Map<string, VillageForm>): FormArea[] {
	const by = new Map<string, FormArea>();
	for (const f of forms.values()) {
		const a = by.get(f.form) ?? { form: f.form, villages: 0, foreign: f.foreign };
		a.villages++;
		by.set(f.form, a);
	}
	return [...by.values()].sort((a, b) => b.villages - a.villages || a.form.localeCompare(b.form));
}

/** Krátká značka morfému z exportu (`morpheme:e9471cb4…` → `e9471c`). */
export const shortMorpheme = (id: string | null) => (id ? id.replace(/^morpheme:/, '').slice(0, 6) : null);

/** Ves → tvar pojmu v průběžném roce: tvar jazyka (linie) největší domácí skupiny vsi ze slovníku v roce. */
export function villageFormsAt(
	home: Map<string, { lineage: string; group: string }>,
	concept: string,
	lexicon: (lineage: string) => Record<string, string> | null | undefined
): Map<string, VillageForm> {
	const out = new Map<string, VillageForm>();
	for (const [village, h] of home) {
		const form = lexicon(h.lineage)?.[concept];
		if (form) out.set(village, { form, group: h.group, lineage: h.lineage, entry: null, foreign: false });
	}
	return out;
}

export interface HistoryLayer {
	form: string;
	year: number;
	/** linie (u protoformy id jazyka zadání) */
	language: string;
	proto: boolean;
	/** vrstva je začátek jazyka (jiná linie než starší vrstva), ne jen změna výslovnosti */
	changed: boolean;
}

export interface HistoryLink {
	id: string;
	history: { year: number; form: string | null }[];
}

/** Linie od jazyka kraje přes předky (`parent`) až ke kořeni; `lineages` je seznam z exportu. */
export function lineageChain(lineages: { id: string; parent: string | null }[], start: string): string[] {
	const by = new Map(lineages.map((l) => [l.id, l]));
	const out: string[] = [];
	for (let id: string | null = start; id && by.has(id) && !out.includes(id); id = by.get(id)?.parent ?? null) out.push(id);
	return out;
}

/** Jazyk zadání (protojazyk) kořenové linie: kód z první její skupiny na začátku. */
export function protoOf(result: ExportV2, root: string): string | null {
	const lin = result.lineages.find((l) => l.id === root);
	const code = new Map(result.groups.map((g) => [g.id, g.code_language]));
	for (const g of [...(lin?.groups_at_start ?? []), ...(lin?.groups ?? [])]) if (code.get(g)) return code.get(g) ?? null;
	return null;
}

/**
 * Vrstvy slova od nejnovější: historie každé linie řetězu (nejnovější první) ořezaná do `maxYear` a před začátek
 * mladší linie, nakonec protoforma. Červený okraj (`changed`) má první vrstva každé linie, za kterou následuje jiná.
 */
export function historyLayers(chain: HistoryLink[], proto: { language: string; form: string | null; year: number } | null, maxYear: number): HistoryLayer[] {
	const groups: HistoryLayer[][] = [];
	let cut = Infinity;
	for (const link of chain) {
		const h = link.history;
		const rows = h.filter((e) => e.form && e.year <= maxYear && e.year < cut).map((e) => ({ form: e.form as string, year: e.year, language: link.id, proto: false, changed: false }));
		if (h.length) cut = Math.min(cut, h[0].year);
		if (rows.length) groups.push(rows.reverse());
	}
	if (proto?.form) groups.push([{ form: proto.form, year: proto.year, language: proto.language, proto: true, changed: false }]);
	const out: HistoryLayer[] = [];
	groups.forEach((g, i) => {
		g.forEach((l, j) => out.push({ ...l, changed: j === g.length - 1 && i < groups.length - 1 }));
	});
	return out;
}
