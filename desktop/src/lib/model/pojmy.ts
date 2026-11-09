// Výpočty obrazovky Pojmy: volby velikosti slovníku, základní pojmy (149 z WOLD s doménou)
// a vlastní pojmy zadání (`concepts` ve světě) včetně ověření formuláře.
import type { WorldSpec } from '$lib/state.svelte';

export type Domain = 'core' | 'learned' | 'culture' | 'religion' | 'power';
export type WordClass = 'noun' | 'verb' | 'uninflected';
export type RelationKind = 'polysemy' | 'derivation' | 'colexification';

/** Velikost základního slovníku, na který je engine kalibrovaný (`vocabulary.default`). */
export const BASE_SIZE = 149;

export const DOMAINS: readonly Domain[] = ['core', 'learned', 'culture', 'religion', 'power'];
export const WORD_CLASSES: readonly WordClass[] = ['noun', 'verb', 'uninflected'];
export const RELATION_KINDS: readonly RelationKind[] = ['polysemy', 'derivation', 'colexification'];

/** Meze ruční frekvence a půjčitelnosti (`ConceptSpec` ve schématu); prázdné = z vazby, jinak průměr katalogu. */
export const FREQUENCY = { min: 0.05, max: 0.9, step: 0.01 } as const;
export const BORROWED = { min: 0, max: 1, step: 0.01 } as const;

/** Vztah k jinému pojmu pro posun významu (`RelatedSpec` ve schématu). */
export interface RelatedSpec {
	concept: string;
	kind?: RelationKind;
	direction?: 'to' | 'from' | 'both' | null;
	weight?: number | null;
}

/** Vlastní pojem zadání (`ConceptSpec` ve schématu; bez prázdných polí). */
export interface CustomConcept {
	id: string;
	gloss?: string;
	wold?: string;
	concepticon?: number;
	domain?: Domain;
	word_class?: WordClass;
	related?: RelatedSpec[];
	frequency?: number;
	borrowed?: number;
}

/** Základních 149 pojmů enginu (`core_list` v src/cee/data/v2_concepts.json) s doménou. */
export const BASE_CONCEPTS: readonly { id: string; domain: Domain }[] = [
	{ id: 'i', domain: 'core' }, { id: 'you', domain: 'core' }, { id: 'we', domain: 'core' },
	{ id: 'this', domain: 'core' }, { id: 'that', domain: 'core' }, { id: 'who', domain: 'learned' },
	{ id: 'what', domain: 'learned' }, { id: 'not', domain: 'core' }, { id: 'all', domain: 'culture' },
	{ id: 'many', domain: 'culture' }, { id: 'one', domain: 'culture' }, { id: 'two', domain: 'culture' },
	{ id: 'big', domain: 'core' }, { id: 'long', domain: 'core' }, { id: 'small', domain: 'core' },
	{ id: 'woman', domain: 'core' }, { id: 'man', domain: 'core' }, { id: 'person', domain: 'core' },
	{ id: 'fish', domain: 'core' }, { id: 'bird', domain: 'core' }, { id: 'dog', domain: 'core' },
	{ id: 'louse', domain: 'core' }, { id: 'tree', domain: 'culture' }, { id: 'seed', domain: 'culture' },
	{ id: 'leaf', domain: 'culture' }, { id: 'root', domain: 'culture' }, { id: 'bark', domain: 'culture' },
	{ id: 'skin', domain: 'core' }, { id: 'flesh', domain: 'core' }, { id: 'blood', domain: 'core' },
	{ id: 'bone', domain: 'core' }, { id: 'grease', domain: 'culture' }, { id: 'egg', domain: 'culture' },
	{ id: 'horn', domain: 'core' }, { id: 'tail', domain: 'core' }, { id: 'feather', domain: 'core' },
	{ id: 'hair', domain: 'core' }, { id: 'head', domain: 'core' }, { id: 'ear', domain: 'core' },
	{ id: 'eye', domain: 'core' }, { id: 'nose', domain: 'core' }, { id: 'mouth', domain: 'core' },
	{ id: 'tooth', domain: 'core' }, { id: 'tongue', domain: 'core' }, { id: 'fingernail', domain: 'core' },
	{ id: 'foot', domain: 'core' }, { id: 'leg', domain: 'core' }, { id: 'knee', domain: 'core' },
	{ id: 'hand', domain: 'core' }, { id: 'belly', domain: 'core' }, { id: 'neck', domain: 'core' },
	{ id: 'breasts', domain: 'core' }, { id: 'heart', domain: 'core' }, { id: 'liver', domain: 'core' },
	{ id: 'drink', domain: 'culture' }, { id: 'eat', domain: 'culture' }, { id: 'bite', domain: 'core' },
	{ id: 'see', domain: 'core' }, { id: 'hear', domain: 'core' }, { id: 'know', domain: 'learned' },
	{ id: 'sleep', domain: 'core' }, { id: 'die', domain: 'core' }, { id: 'kill', domain: 'core' },
	{ id: 'swim', domain: 'core' }, { id: 'fly', domain: 'core' }, { id: 'walk', domain: 'core' },
	{ id: 'come', domain: 'core' }, { id: 'lie', domain: 'core' }, { id: 'sit', domain: 'core' },
	{ id: 'stand', domain: 'core' }, { id: 'give', domain: 'culture' }, { id: 'say', domain: 'learned' },
	{ id: 'sun', domain: 'core' }, { id: 'moon', domain: 'core' }, { id: 'star', domain: 'core' },
	{ id: 'water', domain: 'core' }, { id: 'rain', domain: 'core' }, { id: 'stone', domain: 'core' },
	{ id: 'sand', domain: 'core' }, { id: 'earth', domain: 'core' }, { id: 'cloud', domain: 'core' },
	{ id: 'smoke', domain: 'core' }, { id: 'fire', domain: 'core' }, { id: 'ash', domain: 'core' },
	{ id: 'burn', domain: 'core' }, { id: 'path', domain: 'core' }, { id: 'mountain', domain: 'core' },
	{ id: 'red', domain: 'core' }, { id: 'green', domain: 'core' }, { id: 'yellow', domain: 'core' },
	{ id: 'white', domain: 'core' }, { id: 'black', domain: 'core' }, { id: 'night', domain: 'learned' },
	{ id: 'hot', domain: 'core' }, { id: 'cold', domain: 'core' }, { id: 'full', domain: 'culture' },
	{ id: 'new', domain: 'learned' }, { id: 'good', domain: 'learned' }, { id: 'round', domain: 'core' },
	{ id: 'dry', domain: 'core' }, { id: 'name', domain: 'learned' }, { id: 'father', domain: 'core' },
	{ id: 'mother', domain: 'core' }, { id: 'child', domain: 'core' }, { id: 'family', domain: 'core' },
	{ id: 'house', domain: 'culture' }, { id: 'village', domain: 'power' }, { id: 'town', domain: 'power' },
	{ id: 'road', domain: 'core' }, { id: 'river', domain: 'core' }, { id: 'sea', domain: 'core' },
	{ id: 'forest', domain: 'core' }, { id: 'field', domain: 'culture' }, { id: 'wind', domain: 'core' },
	{ id: 'thunder', domain: 'core' }, { id: 'day', domain: 'learned' }, { id: 'year', domain: 'learned' },
	{ id: 'morning', domain: 'learned' }, { id: 'food', domain: 'culture' }, { id: 'grain', domain: 'culture' },
	{ id: 'salt', domain: 'culture' }, { id: 'animal', domain: 'core' }, { id: 'horse', domain: 'core' },
	{ id: 'boat', domain: 'core' }, { id: 'trade', domain: 'culture' }, { id: 'king', domain: 'power' },
	{ id: 'law', domain: 'power' }, { id: 'war', domain: 'power' }, { id: 'peace', domain: 'power' },
	{ id: 'god', domain: 'religion' }, { id: 'spirit', domain: 'learned' },
	{ id: 'ritual', domain: 'religion' }, { id: 'write', domain: 'learned' }, { id: 'read', domain: 'learned' },
	{ id: 'speak', domain: 'learned' }, { id: 'language', domain: 'learned' },
	{ id: 'friend', domain: 'power' }, { id: 'enemy', domain: 'power' }, { id: 'work', domain: 'culture' },
	{ id: 'make', domain: 'culture' }, { id: 'carry', domain: 'core' }, { id: 'open', domain: 'core' },
	{ id: 'close', domain: 'core' }, { id: 'near', domain: 'core' }, { id: 'far', domain: 'core' },
	{ id: 'old', domain: 'learned' }, { id: 'young', domain: 'learned' }, { id: 'fast', domain: 'learned' },
	{ id: 'slow', domain: 'learned' },
];

/** Vlastní pojmy ve světě. */
export function customConcepts(world: WorldSpec | null): CustomConcept[] {
	return (world?.concepts as CustomConcept[] | undefined) ?? [];
}

/** Velikost slovníku ve světě; bez zápisu platí základní. */
export function sizeOf(world: WorldSpec | null): number {
	const n = world?.vocabulary;
	return typeof n === 'number' ? n : BASE_SIZE;
}

/** Volby velikosti: předvolby z enginu a jeho maximum, bez duplicit, od nejmenší. */
export function sizeOptions(vocabulary: { presets: number[]; max: number }): number[] {
	return [...new Set([...vocabulary.presets, vocabulary.max])].sort((a, b) => a - b);
}

/** Násobek běhu oproti základnímu slovníku: pod dvě jednotky s desetinou, výš celé číslo. */
export function sizeFactor(n: number, base = BASE_SIZE): number {
	const ratio = n / base;
	return ratio < 2 ? Math.round(ratio * 10) / 10 : Math.round(ratio);
}

/** Pojem bez vazby na WOLD i Concepticon je vymyšlený (engine mu dogeneruje vlastnosti). */
export function isInvented(c: Pick<CustomConcept, 'wold' | 'concepticon'>): boolean {
	return !c.wold && c.concepticon == null;
}

/** Hodnoty formuláře jako text; prázdné pole znamená „nenastaveno“. */
export interface Draft {
	id: string;
	gloss: string;
	domain: string;
	word_class: string;
	wold: string;
	concepticon: string;
	related: string;
	relation_kind: string;
	/** text čísla; prázdné = z vazby (ruční režim je v obrazovce) */
	frequency: string;
	borrowed: string;
}

export const emptyDraft = (): Draft => ({
	id: '',
	gloss: '',
	domain: '',
	word_class: '',
	wold: '',
	concepticon: '',
	related: '',
	relation_kind: 'polysemy',
	frequency: '',
	borrowed: ''
});

export function draftOf(c: CustomConcept): Draft {
	const rel = c.related?.[0];
	return {
		id: c.id,
		gloss: c.gloss ?? '',
		domain: c.domain ?? '',
		word_class: c.word_class ?? '',
		wold: c.wold ?? '',
		concepticon: c.concepticon != null ? String(c.concepticon) : '',
		related: rel?.concept ?? '',
		relation_kind: rel?.kind ?? 'polysemy',
		frequency: c.frequency != null ? String(c.frequency) : '',
		borrowed: c.borrowed != null ? String(c.borrowed) : ''
	};
}

/** Pojem ze formuláře; prázdná pole se do zadání nepíšou. */
export function conceptOf(d: Draft): CustomConcept {
	const c: CustomConcept = { id: d.id.trim() };
	if (d.gloss.trim()) c.gloss = d.gloss.trim();
	if (d.domain) c.domain = d.domain as Domain;
	if (d.word_class) c.word_class = d.word_class as WordClass;
	if (d.wold.trim()) c.wold = d.wold.trim();
	if (d.concepticon.trim()) c.concepticon = Number(d.concepticon.trim());
	if (d.related) c.related = [{ concept: d.related, kind: d.relation_kind as RelationKind, direction: null, weight: null }];
	// mimo meze se číslo do zadání nepíše (formulář to ukáže jako chybu a nedovolí uložit)
	const frequency = parseRatio(d.frequency, FREQUENCY);
	if (frequency != null) c.frequency = frequency;
	const borrowed = parseRatio(d.borrowed, BORROWED);
	if (borrowed != null) c.borrowed = borrowed;
	return c;
}

/** Číslo z formuláře (desetinná čárka i tečka) v mezích; prázdné nebo mimo meze je `null`. */
export function parseRatio(text: string, range: { min: number; max: number }): number | null {
	const s = text.trim().replace(',', '.');
	if (!s) return null;
	const n = Number(s);
	return Number.isFinite(n) && n >= range.min && n <= range.max ? n : null;
}

/** Vyplněné, ale nečitelné nebo mimo meze číslo; prázdné pole není chyba. */
export function ratioProblem(text: string, range: { min: number; max: number }): boolean {
	return text.trim() !== '' && parseRatio(text, range) === null;
}

/** Id pojmu jako v schématu: písmeno nebo číslice či podtržítko, pak i tečka a pomlčka. */
const ID = /^[\p{L}\p{N}_][\p{L}\p{N}_.-]*$/u;

export interface DraftProblems {
	id: 'empty' | 'bad' | 'taken' | null;
	concepticon: boolean;
	frequency: boolean;
	borrowed: boolean;
}

/** Chyby formuláře; `taken` jsou id, která už ve světě jsou (základní i vlastní kromě upravovaného). */
export function checkDraft(d: Draft, taken: Set<string>): DraftProblems {
	const id = d.id.trim();
	let idProblem: DraftProblems['id'] = null;
	if (!id) idProblem = 'empty';
	else if (!ID.test(id)) idProblem = 'bad';
	else if (taken.has(id)) idProblem = 'taken';
	const n = d.concepticon.trim();
	const concepticon = n !== '' && !(/^\d+$/.test(n) && Number(n) >= 1);
	return {
		id: idProblem,
		concepticon,
		frequency: ratioProblem(d.frequency, FREQUENCY),
		borrowed: ratioProblem(d.borrowed, BORROWED)
	};
}

/** Hledání v seznamu: bez velikosti písmen, v id i v popisku (`label`). */
export function filterConcepts<T extends { id: string }>(list: readonly T[], query: string, label: (c: T) => string): T[] {
	const q = query.trim().toLowerCase();
	if (!q) return [...list];
	return list.filter((c) => c.id.toLowerCase().includes(q) || label(c).toLowerCase().includes(q));
}
