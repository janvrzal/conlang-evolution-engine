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
	entry: LexEntry;
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
