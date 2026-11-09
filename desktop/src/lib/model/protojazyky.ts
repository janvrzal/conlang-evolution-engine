// Protojazyky zadání: tabulka hlásek, úpravy inventáře a potomci protojazyka ve výsledku.
import type { WorldSpec } from '$lib/state.svelte';
import type { ExportV2, FrameV2 } from './export';
import { speakers } from './languages';

export type Place = { id: string; segments: string[] };
export type Manner = { id: string; segments: string[] };

/** Místa tvoření (sloupce tabulky souhlásek). */
export const PLACES: Place[] = [
	{ id: 'bilabial', segments: ['p', 'b', 'm', 'ɸ', 'β', 'w'] },
	{ id: 'labiodental', segments: ['f', 'v', 'ɱ', 'ʋ'] },
	{ id: 'dental', segments: ['θ', 'ð'] },
	{ id: 'alveolar', segments: ['t', 'd', 'n', 's', 'z', 'r', 'ɾ', 'l', 'ɬ', 't͡s', 'd͡z'] },
	{ id: 'postalveolar', segments: ['ʃ', 'ʒ', 't͡ʃ', 'd͡ʒ'] },
	{ id: 'palatal', segments: ['c', 'ɟ', 'ɲ', 'ç', 'ʝ', 'j', 'ʎ'] },
	{ id: 'velar', segments: ['k', 'ɡ', 'ŋ', 'x', 'ɣ', 'kʷ', 'ɡʷ'] },
	{ id: 'uvular', segments: ['q', 'ɢ', 'χ', 'ʁ'] },
	{ id: 'glottal', segments: ['ʔ', 'h', 'ɦ'] }
];

/** Způsoby tvoření (řádky tabulky souhlásek). */
export const MANNERS: Manner[] = [
	{ id: 'stop', segments: ['p', 'b', 't', 'd', 'c', 'ɟ', 'k', 'ɡ', 'kʷ', 'ɡʷ', 'q', 'ɢ', 'ʔ'] },
	{ id: 'nasal', segments: ['m', 'ɱ', 'n', 'ɲ', 'ŋ'] },
	{ id: 'fricative', segments: ['ɸ', 'β', 'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ', 'ç', 'ʝ', 'x', 'ɣ', 'χ', 'ʁ', 'h', 'ɦ', 'ɬ'] },
	{ id: 'affricate', segments: ['t͡s', 'd͡z', 't͡ʃ', 'd͡ʒ'] },
	{ id: 'trill', segments: ['r', 'ɾ'] },
	{ id: 'approximant', segments: ['w', 'ʋ', 'j', 'l', 'ʎ'] }
];

export const VOWELS = ['i', 'y', 'ɨ', 'u', 'e', 'ø', 'ə', 'o', 'ɛ', 'ɔ', 'æ', 'a', 'ɑ'];
export const TONES = ['˥', '˦', '˧', '˨', '˩', '˥˩', '˩˥'];
export const STRESSES = ['initial', 'second', 'antepenult', 'penult', 'final', 'weight'] as const;
export const SYLLABLES = ['simple', 'moderate', 'complex', 'random'] as const;
export const GRAMMARS = ['default', 'substrate', 'full'] as const;
export const PROCESS_FAMILIES = ['coda_loss', 'palatalization', 'spirantization', 'voicing', 'vowel_reduction', 'apocope', 'syncope', 'tonogenesis_onset', 'vowel_shift', 'final_devoicing'] as const;
export const FUNCTIONS = ['PAST', 'FUTURE', 'PL', 'OBJ', 'DEFINITE', 'ASPECT', 'NEG', 'ORDER'] as const;
export const CONSTRUCTION_KINDS = ['synthetic', 'analytic', 'pre', 'post', 'fixed', 'zero'] as const;

export type Language = WorldSpec['languages'][number];

/** Pole protojazyka, která `WorldSpec` zná jen jako `unknown` (schéma enginu: LanguageSpec). */
export interface ProtoExtras {
	tones?: string[];
	syllables?: 'simple' | 'moderate' | 'complex' | null;
	stress_strength?: 'weak' | 'strong';
	constructions?: Record<string, { kind: string; source?: string | null }>;
	suffixes?: string[];
	endings?: Record<string, unknown>;
	processes?: { family: string; label: string; share: number }[];
}
export type ProtoLanguage = Language & ProtoExtras;

/** Přepne hlásku v seznamu (bez duplicit, pořadí zůstává). */
export function toggleSegment(list: string[] | undefined, seg: string): string[] {
	const cur = list ?? [];
	return cur.includes(seg) ? cur.filter((x) => x !== seg) : [...cur, seg];
}

/** Hlásky inventáře, které tabulka nezná (zadané ručně, jiné IPA). */
export function extraSegments(list: string[] | undefined, known: string[]): string[] {
	return (list ?? []).filter((s) => !known.includes(s));
}

export const KNOWN_CONSONANTS = [...new Set(PLACES.flatMap((p) => p.segments))];

/** Hlásky patřící do buňky tabulky (průnik místa a způsobu). */
export function cell(place: Place, manner: Manner): string[] {
	return place.segments.filter((s) => manner.segments.includes(s));
}

/** Počet krajů zadání, kde se mluví daným protojazykem (kraj bez `language` mluví prvním). */
export function regionCount(world: WorldSpec, id: string): number {
	const first = world.languages[0]?.id;
	return world.regions.filter((r) => (r.language ?? first) === id).length;
}

/** Nové ID protojazyka, které v zadání ještě není. */
export function newLanguageId(world: WorldSpec): string {
	let n = world.languages.length + 1;
	while (world.languages.some((l) => l.id === `proto${n}`)) n++;
	return `proto${n}`;
}

export interface Descendant {
	id: string;
	speakers: number;
}

/**
 * Jazyky koncového snímku, které patří do rodiny protojazyka `family` (index v zadání),
 * seřazené podle počtu mluvčích doma; jazyky bez mluvčích se vynechají.
 */
export function descendants(frame: FrameV2 | null, result: ExportV2 | null, families: Map<string, number>, family: number): Descendant[] {
	if (!frame || !result) return [];
	const domainOf = new Map(result.groups.map((g) => [g.id, g.domain]));
	const spoken = speakers(frame.groups, domainOf);
	return [...spoken.entries()]
		.filter(([id, n]) => n > 0 && families.get(id) === family)
		.map(([id, n]) => ({ id, speakers: n }))
		.sort((a, b) => b.speakers - a.speakers);
}

/** Pojmy, k nimž jde zadat vlastní slovo: slova autora, tvary protojazyka z běhu a pojmy slovníku. */
export function wordConcepts(lang: Language, result: ExportV2 | null): string[] {
	const ids = new Set(Object.keys(lang.words ?? {}));
	for (const c of Object.keys(protoForms(result, lang.id) ?? {})) ids.add(c);
	const sample = result ? Object.values(result.lexicon)[0] : undefined;
	for (const c of Object.keys(sample ?? {})) ids.add(c);
	return [...ids];
}

/** Pojmy pro ukázku „Jak jazyk zní“ (základní slovní zásoba). */
export const BASIC_CONCEPTS = ['water', 'fire', 'stone', 'person', 'sun', 'moon', 'mother', 'father', 'dog', 'eye', 'hand', 'tree'];

/** Tvary protojazyka `id` ze slovníku protojazyků na startu; null bez běhu nebo bez tohoto jazyka v něm. */
export function protoForms(result: ExportV2 | null, id: string | undefined): Record<string, string> | null {
	if (!result || !id) return null;
	return result.proto_lexicon?.[id]?.forms ?? null;
}

/** Původ tvaru: slovo zadal autor (`words`), nebo ho složil engine; bez tvaru a bez autora null. */
export type FormOrigin = 'author' | 'engine' | null;

export interface FormRow {
	concept: string;
	/** tvar z běhu (IPA), null bez běhu */
	form: string | null;
	origin: FormOrigin;
}

/** Řádky pro pojmy: tvar z běhu a zdroj (autor, nebo engine, pokud tvar je). */
export function formRows(lang: Language, forms: Record<string, string> | null, concepts: readonly string[]): FormRow[] {
	return concepts.map((concept) => {
		const author = !!lang.words?.[concept];
		const form = forms?.[concept] ?? null;
		return { concept, form, origin: author ? 'author' : form ? 'engine' : null };
	});
}
