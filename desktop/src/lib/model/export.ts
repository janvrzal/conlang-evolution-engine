// Typy exportu enginu v2 (formát cee-v2/1, GET /api/v2/runs/{id}/result) a průběžného snímku
// (GET /api/v2/runs/{id} → frames). Pole odpovídají rust/cee_engine (export.rs, frame).
import type { NamesExport } from './jmena';

export interface Toponym {
	name: string;
	ipa: string;
	meaning: string;
	current_language: string | null;
	origin_language: string | null;
	pattern: string;
	substrate: boolean;
	urban: boolean;
	exonyms: Record<string, string>;
}

export interface Territory {
	id: string;
	/** world | region | settlement */
	level: string;
	name: string;
	native_language: string | null;
	parent: string | null;
	position: [number, number] | null;
	terrain: string | null;
	toponym?: Toponym;
}

export interface Group {
	id: string;
	territory: string;
	community: string;
	/** home | public */
	domain: string;
	population: number;
	/** linie pozorovaného jazyka („lineage:…“) */
	observed_language: string | null;
	/** protojazyk (rodina) */
	code_language: string;
	written: boolean;
	literacy: number;
	schooling: number;
	loyalty: number;
	prestige: number;
	openness: number;
	l2_share: number;
	standard: string | null;
	revival: number;
	root_retention?: number;
	position: [number, number] | null;
	aggregate: boolean;
	[key: string]: unknown;
}

export interface Lineage {
	id: string;
	parent: string | null;
	start_year: number;
	end_year: number | null;
	groups_at_start: string[];
	groups: string[];
	endonym: string | null;
	origin_region: string | null;
}

export interface DialectFact {
	groups: string[];
	lineage: string | null;
	regions: string[];
	direction: string;
	terrain: string | null;
	sole: boolean;
}

export interface StateRecord {
	id: string;
	name: string;
	capital: string;
	seat: string;
	language: string;
	/** tolerant | promoted | enforced */
	policy: string;
	border: string;
	centralization: string;
	regions: string[];
	standard: string | null;
}

export interface Census {
	home: Record<string, number>;
	public: Record<string, number>;
	state: string | null;
}

export interface LexEntry {
	form: string;
	/** inherited | loan | derived | compound | renewal | clipping | metathesis | dissimilation | … */
	origin: string;
	language: string;
	loan: boolean;
	root: string | null;
	base: string | null;
	since: number | null;
	sources: string[];
}

export interface GrammarSlot {
	kind: string;
	stage: string | null;
	exponent: string | null;
	source: string | null;
	donor: string | null;
	order: string | null;
	reinforcer: string | null;
}

export interface EngineEvent {
	kind: string;
	year: number;
	tick?: number;
	/** u `study_case`: štítek, druh události zadání a její pořadí v zadání */
	label?: string;
	event_kind?: string;
	spec_event?: number;
	[key: string]: unknown;
}

/** Slovník jazyka: skupina, podle které se tvary berou, a pojem → tvar (IPA). */
export interface LanguageLexicon {
	group: string;
	forms: Record<string, string>;
}

/** Zvuková změna jazyka (`change_history`, kind sound). */
export interface SoundChange {
	kind: 'sound';
	variable: string;
	family: string;
	target: string;
	operation: string;
	features: unknown;
	/** IPA výsledné hlásky (nahrazení, vložení, splynutí); `segment_id` je její číslo */
	segment: string | null;
	segment_id?: number | null;
	left: string | null;
	right: string | null;
	stress: string | null;
	medial: boolean | null;
	/** rok vzniku */
	year: number;
	/** vsi (skupiny): rok ustálení, rok uzavření, relikty */
	groups: { group: string; year: number; closed: number | null; relics: unknown }[];
}

/** Analogie v jazyce (`change_history`, kind analogy). */
export interface AnalogyChange {
	kind: 'analogy';
	variable: string;
	operation: string;
	concept: string | null;
	cell: string | null;
	year: number;
	groups: { group: string; year: number }[];
}

/** Změny po jazycích; `language: null` = skupiny, které už nežijí. */
export interface ChangeHistory {
	language: string | null;
	groups: string[];
	changes: (SoundChange | AnalogyChange)[];
}

export interface ExportV2 {
	format: 'cee-v2/1';
	seed: number;
	start_year: number;
	year: number;
	tick: number;
	territories: Territory[];
	groups: Group[];
	lineages: Lineage[];
	dialect_facts: DialectFact[];
	states: StateRecord[];
	census: Record<string, Census>;
	borders: { factor: number; regions: string[]; states: (string | null)[] }[];
	/** skupina → pojem → slovo */
	lexicon: Record<string, Record<string, LexEntry>>;
	/** skupina → mluvnická kategorie → vyjádření */
	grammar: Record<string, Record<string, GrammarSlot>>;
	standards: Record<string, string>;
	onomastics: { toponyms: Record<string, Toponym>; states: Record<string, unknown>; [key: string]: unknown };
	snapshots: { year: number; tick: number; languages: Record<string, string[]>; dialects: string[][] }[];
	/** Slovník protojazyků na startu: jazyk zadání → tvary. */
	proto_lexicon?: Record<string, LanguageLexicon>;
	/** Dnešní slovník každého pozorovaného jazyka (linie) podle největší domácí skupiny. */
	lexicon_by_language?: Record<string, LanguageLexicon>;
	/** Zvukové změny a analogie po jazycích s roky a vesnicemi. */
	change_history?: ChangeHistory[];
	/** Události. Plný export jich má miliony (milníky zvukových změn); aplikace dostává jen dějinné a jazykové. */
	events: EngineEvent[];
	/** Souhrn všech událostí po stoletích: „1800“ → druh → počet. Zatím jen ve vzorku (scripts/fixture.py), server ho má doplnit. */
	event_summary?: Record<string, Record<string, number>>;
	/** Počet událostí podle druhu za celý běh. */
	event_counts?: Record<string, number>;
	/** Jména s historií (modul jmen, dok. 34); bez modulu chybí. */
	names?: NamesExport | null;
	/** Jméno světa z modulu jmen. */
	world_name?: string | null;
	links?: { kind: string; source: string; target: string; strength: number }[];
}

/** Průběžný snímek běhu (po 100 letech a v end_year). Bez slovníku a mluvnice. */
export interface FrameV2 {
	year: number;
	tick: number;
	groups: { id: string; population: number; observed_language: string | null; l2_share: number }[];
	languages: Record<string, string[]>;
	endonyms: Record<string, string | null>;
	dialects: string[][];
	dialect_facts: DialectFact[];
	states: { id: string; name: string; regions: string[] }[];
	census: Record<string, Census>;
}
