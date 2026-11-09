// Výpočty obrazovky Kronika: události dějin autora (zadání) a dějin běhu (výsledek), jejich popisky,
// sloučení stejných událostí roku a souhrn drobných změn po stoletích (result.event_summary).
import type { MessageKey } from '$lib/i18n.svelte';
import { caseLabelOf, isStudyCase } from './dejiny';

export type Source = 'author' | 'history';
/**
 * Filtr kroniky: dějiny autora, společnost (přechody, kodifikace, osady), jazyky (vznik a zánik),
 * studijní případy (události zadání se `study_case` a události běhu `study_case`; mají přednost před třídou zdroje).
 */
export type Cls = 'author' | 'soc' | 'lang' | 'case';
export type SummaryId = 'sound' | 'stress' | 'analogy' | 'innovation' | 'grammar' | 'extinct';
export type Tr = (key: MessageKey, params?: Record<string, string | number>) => string;

/** Surová událost (world.events nebo result.events). */
export type RawEvent = { kind: string; year: number } & Record<string, unknown>;

export interface Detail {
	term: string;
	value: string;
}

export interface KEvent {
	/** a<index> pro dějiny autora, h<index> pro dějiny běhu */
	key: string;
	/** index v world.events resp. result.events */
	index: number;
	source: Source;
	cls: Cls;
	year: number;
	kind: string;
	kindLabel: string;
	title: string;
	text: string;
	details: Detail[];
	/** štítek studijního případu (text z `study_case` zadání nebo `label` běhu), jinak prázdný */
	caseLabel: string;
	/** u studijního případu běhu: index události zadání (`spec_event`), na kterou odkazuje Dějiny */
	specEvent: number | null;
	/** text pro hledání (malá písmena) */
	search: string;
}

/** Řádek kroniky: stejné události (zdroj, rok, druh) sloučené s počtem. */
export interface KRow {
	key: string;
	source: Source;
	cls: Cls;
	year: number;
	kind: string;
	kindLabel: string;
	title: string;
	text: string;
	count: number;
	members: KEvent[];
}

/** Jeden druh drobné změny v rozpisu století (z result.event_summary). */
export interface KindCount {
	kind: string;
	label: string;
	value: number;
	/** vysvětlení druhu, jen u milníků a uzavřených procesů */
	why: string;
}

export interface KCentury {
	key: number;
	from: number;
	to: number;
	summary: { id: SummaryId; value: number }[];
	/** rozpis po druzích, od nejčastějšího; milníky a uzavřené procesy jsou poslední */
	kinds: KindCount[];
	rows: KRow[];
}

export interface KronikaNames {
	/** jméno kraje (id kraje) */
	region(id: string): string;
	/** jméno jazyka z výsledku (linie) */
	lineage(id: string): string;
	/** jméno jazyka ze zadání (kód jazyka) */
	language(code: string): string;
	/** jméno státu */
	state(id: string): string;
	/** je id krajem světa? (odděluje kraj od vsi a skupiny) */
	known(id: string): boolean;
}

export interface KronikaContext {
	tr: Tr;
	names: KronikaNames;
}

/** Souhrn drobných změn ve výsledku: který druh enginu patří ke kterému řádku souhrnu. */
export const SUMMARY_GROUPS: Record<SummaryId, string[]> = {
	sound: ['established', 'phonologized'],
	stress: ['stress_rule_changed', 'stress_strength_changed'],
	analogy: ['analogy'],
	innovation: ['innovation'],
	grammar: ['grammaticalized', 'exapted'],
	extinct: ['extinct']
};
const SUMMARY_ORDER: SummaryId[] = ['sound', 'stress', 'analogy', 'innovation', 'grammar', 'extinct'];

/** Drobné změny: jen v souhrnu století, jako řádky se nezobrazují. */
const SUMMARY_ONLY = new Set(['stress_rule_changed', 'stress_strength_changed', 'grammaticalized', 'exapted']);
const LANG_KINDS = new Set(['language_emerged', 'language_split', 'language_ended']);
/** Druhy, jejichž název je v sdíleném kind.* (cs.ts, en.ts). */
const CORE_KIND = new Set([
	'state', 'language_policy', 'annexation', 'secession', 'collapse', 'border_policy', 'lingua_franca', 'standard', 'schools',
	'revival', 'preserve', 'identity', 'immigration', 'settlement', 'elite', 'conquest', 'migration', 'codification', 'printing',
	'schooling', 'revival_movement', 'bilingualism', 'nativization', 'transmission_stopped', 'transmission_resumed', 'language_shift',
	'language_emerged', 'language_split', 'language_ended'
]);
/** Druhy jen z této obrazovky (kronika.kind.*), včetně těch, které jsou jen v souhrnu století. */
const OWN_KIND = new Set([
	'stress_rule_changed', 'stress_strength_changed', 'grammaticalized', 'exapted', 'innovation', 'extinct', 'analogy',
	'established', 'phonologized', 'milestone', 'process_closed', 'study_case'
]);
/** Druhy rozpisu, které jdou na konec století (v tomto pořadí) s vysvětlením. */
const LAST_KINDS = ['milestone', 'process_closed'] as const;

const WORDS = {
	policy: ['tolerant', 'promoted', 'enforced'],
	border: ['open', 'normal', 'closed'],
	literacy: ['elite', 'towns', 'mass'],
	identity: ['shared', 'distinct', 'strong'],
	strength: ['movement', 'national'],
	coverage: ['towns', 'mass']
} as const;
type WordGroup = keyof typeof WORDS;

const str = (x: unknown): string => (typeof x === 'string' ? x : x == null ? '' : String(x));
const list = (x: unknown): string[] => (Array.isArray(x) ? x.map(str).filter(Boolean) : []);
const pct = (x: unknown): string => String(Math.round(Number(x) * 100));

/** Klíč názvu druhu události, nebo null, když ho katalog nezná. */
export function kindKey(kind: string): MessageKey | null {
	if (CORE_KIND.has(kind)) return `kind.${kind}` as MessageKey;
	if (OWN_KIND.has(kind)) return `kronika.kind.${kind}` as MessageKey;
	return null;
}

export function kindLabel(kind: string, tr: Tr): string {
	const key = kindKey(kind);
	return key ? tr(key) : kind;
}

/**
 * Rozpis drobných změn jednoho století: druhy s počtem, od nejčastějšího (při shodě podle názvu);
 * milníky a uzavřené procesy na konci. Nulové počty se vynechají.
 */
export function kindCounts(counts: Record<string, number> | undefined, tr: Tr): KindCount[] {
	const entries = Object.entries(counts ?? {}).filter(([, n]) => Number(n) > 0);
	const main = entries
		.filter(([kind]) => !(LAST_KINDS as readonly string[]).includes(kind))
		.sort(([ka, na], [kb, nb]) => nb - na || ka.localeCompare(kb));
	const last = LAST_KINDS.flatMap((kind) => entries.filter(([k]) => k === kind));
	return [...main, ...last].map(([kind, value]) => ({
		kind,
		label: kindLabel(kind, tr),
		value: Number(value),
		why: (LAST_KINDS as readonly string[]).includes(kind) ? tr(`kronika.why.${kind}` as MessageKey) : ''
	}));
}

export function classOf(source: Source, kind: string): Cls {
	if (source === 'author') return 'author';
	return LANG_KINDS.has(kind) ? 'lang' : 'soc';
}

/**
 * Id kraje z id skupiny nebo vsi: „m07-02-v0>seren“ → „m07-02“, „m03-06+m06-03-v0“ → „m03-06“.
 * Při pochybnosti vezme kandidáta, který je krajem světa.
 */
export function regionId(id: string, known: (id: string) => boolean = () => false): string {
	const base = id.split(/[>+]/)[0];
	const candidates = [base, base.replace(/-v\d+$/, ''), base.replace(/-\d+$/, '')];
	return candidates.find((c) => known(c)) ?? base.replace(/-v\d+$/, '');
}

/** Popisek události: nadpis, věta a řádky Karty (Stát, Kraje, Jazyk…). Druh bez popisu má jen název. */
function describe(kind: string, e: RawEvent, ctx: KronikaContext): { title: string; text: string; details: Detail[] } {
	const { tr, names } = ctx;
	const T = (key: string, params?: Record<string, string | number>) => tr(key as MessageKey, params);
	const details: Detail[] = [];
	const add = (term: string, value: string) => {
		if (value) details.push({ term: T(term), value });
	};
	const region = (id: unknown) => names.region(regionId(str(id), names.known));
	const regions = (ids: unknown) => [...new Set(list(ids).map((id) => regionId(id, names.known)))].map((id) => names.region(id)).join(', ');
	const state = (id: unknown) => names.state(str(id));
	const word = (group: WordGroup, value: unknown) => {
		const v = str(value);
		return (WORDS[group] as readonly string[]).includes(v) ? T(`kronika.${group}.${v}`) : v;
	};
	const language = (code: unknown) => names.language(str(code));
	const lineage = (id: unknown) => names.lineage(str(id));

	switch (kind) {
		case 'state': {
			const name = str(e.name) || state(e.id);
			add('kronika.term.capital', region(e.capital ?? e.seat));
			add('kronika.term.regions', regions(e.regions));
			const policy = word('policy', e.policy);
			const border = word('border', e.border);
			const text = border ? T('kronika.ev.state.text', { policy, border }) : policy ? T('kronika.ev.state.policy', { policy }) : '';
			return { title: T('kronika.ev.state.title', { name }), text, details };
		}
		case 'annexation':
			add('kronika.term.state', state(e.state));
			add('kronika.term.regions', regions(e.regions));
			return { title: T('kronika.ev.annexation.title', { state: state(e.state), regions: regions(e.regions) }), text: '', details };
		case 'secession': {
			const name = state(e.state ?? e.id);
			add('kronika.term.regions', regions(e.regions));
			return { title: T('kronika.ev.secession.title', { state: name }), text: T('kronika.ev.secession.text', { regions: regions(e.regions) }), details };
		}
		case 'collapse': {
			const name = state(e.state);
			add('kronika.term.regions', regions(e.regions));
			return { title: T('kronika.ev.collapse.title', { state: name }), text: T('kronika.ev.collapse.text', { regions: regions(e.regions) }), details };
		}
		case 'language_policy':
			add('kronika.term.state', state(e.state));
			return { title: T('kronika.ev.language_policy.title', { state: state(e.state), policy: word('policy', e.policy) }), text: '', details };
		case 'border_policy':
			add('kronika.term.state', state(e.state));
			return { title: T('kronika.ev.border_policy.title', { state: state(e.state), border: word('border', e.border) }), text: '', details };
		case 'lingua_franca':
			add('kronika.term.from', region(e.source));
			add('kronika.term.regions', regions(e.regions));
			return {
				title: T('kronika.ev.lingua_franca.title', { source: region(e.source) }),
				text: T('kronika.ev.lingua_franca.text', { regions: regions(e.regions) }),
				details
			};
		case 'standard':
			add('kronika.term.state', state(e.of));
			return {
				title: T('kronika.ev.standard.title', { state: state(e.of) }),
				text: T('kronika.ev.standard.text', { literacy: word('literacy', e.literacy) }),
				details
			};
		case 'codification':
			add('kronika.term.from', region(e.source));
			return { title: T('kronika.ev.codification.title', { source: region(e.source) }), text: T('kronika.ev.codification.text'), details };
		case 'printing':
			return { title: T('kronika.ev.printing.title'), text: T('kronika.ev.printing.text'), details };
		case 'schools':
			add('kronika.term.state', state(e.of));
			add('kronika.term.coverage', word('coverage', e.coverage));
			return {
				title: T('kronika.ev.schools.title', { state: state(e.of) }),
				text: T('kronika.ev.schools.text', { coverage: word('coverage', e.coverage) }),
				details
			};
		case 'schooling':
			return { title: T('kronika.ev.schooling.title'), text: T('kronika.ev.schooling.text', { pct: pct(e.schooling) }), details };
		case 'preserve':
			add('kronika.term.regions', regions(e.regions));
			return { title: T('kronika.ev.preserve.title', { regions: regions(e.regions) }), text: T('kronika.ev.preserve.text'), details };
		case 'identity':
			add('kronika.term.regions', regions(e.regions));
			return {
				title: T('kronika.ev.identity.title', { regions: regions(e.regions) }),
				text: T('kronika.ev.identity.text', { identity: word('identity', e.identity) }),
				details
			};
		case 'immigration':
			add('kronika.term.regions', regions(e.regions));
			return {
				title: T('kronika.ev.immigration.title', { regions: regions(e.regions) }),
				text: T('kronika.ev.immigration.text', { pct: pct(e.immigration) }),
				details
			};
		case 'revival':
		case 'revival_movement': {
			const ids = list(e.regions).length ? e.regions : e.speakers;
			add('kronika.term.regions', regions(ids));
			return {
				title: T('kronika.ev.revival.title', { regions: regions(ids) }),
				text: T('kronika.ev.revival.text', { strength: word('strength', e.strength) }),
				details
			};
		}
		case 'settlement':
			add('kronika.term.from', region(e.from));
			add('kronika.term.to', region(e.to));
			add('kronika.term.share', `${pct(e.share)} %`);
			return {
				title: T('kronika.ev.settlement.title', { from: region(e.from), to: region(e.to) }),
				text: T('kronika.ev.settlement.text', { pct: pct(e.share), n: Number(e.settlements ?? 1) }),
				details
			};
		case 'elite': {
			const subjects = regions(e.subjects);
			add('kronika.term.from', region(e.from));
			add('kronika.term.seat', region(e.seat));
			add('kronika.term.subjects', subjects);
			add('kronika.term.prestige', str(e.prestige));
			return {
				title: T('kronika.ev.elite.title', { from: region(e.from), seat: region(e.seat) }),
				text: T('kronika.ev.elite.text', { subjects, prestige: str(e.prestige) }),
				details
			};
		}
		case 'conquest': {
			const subjects = list(e.subjects).map((s) => s.replace('@', ''));
			const from = region(e.conqueror);
			add('kronika.term.from', from);
			add('kronika.term.subjects', regions(subjects));
			return {
				title: T('kronika.ev.conquest.title', { from, subjects: regions(subjects) }),
				text: T('kronika.ev.conquest.text'),
				details
			};
		}
		case 'migration': {
			const [target = '', source = ''] = str(e.target).split('+');
			add('kronika.term.from', region(source));
			add('kronika.term.to', region(target));
			return {
				title: T('kronika.ev.migration.title', { to: region(target) }),
				text: T('kronika.ev.migration.text', { from: region(source) }),
				details
			};
		}
		case 'bilingualism':
			add('kronika.term.region', region(e.group));
			add('kronika.term.language', language(e.language));
			add('kronika.term.people', str(e.population));
			return {
				title: T('kronika.ev.bilingualism.title', { region: region(e.group), language: language(e.language) }),
				text: T('kronika.ev.bilingualism.text', { people: str(e.population) }),
				details
			};
		case 'nativization':
			add('kronika.term.region', region(e.group));
			add('kronika.term.language', language(e.language));
			return { title: T('kronika.ev.nativization.title', { region: region(e.group) }), text: T('kronika.ev.nativization.text'), details };
		case 'transmission_stopped':
		case 'transmission_resumed':
			add('kronika.term.region', region(e.group));
			add('kronika.term.language', language(e.language));
			return { title: T(`kronika.ev.${kind}.title`, { region: region(e.group) }), text: '', details };
		case 'language_shift':
			add('kronika.term.region', region(e.group));
			add('kronika.term.language', language(e.language));
			return {
				title: T('kronika.ev.language_shift.title', { region: region(e.group) }),
				text: T('kronika.ev.language_shift.text', { language: language(e.target_language) }),
				details
			};
		case 'language_emerged': {
			const n = list(e.groups).length;
			add('kronika.term.language', lineage(e.lineage));
			return {
				title: T('kronika.ev.language_emerged.title', { language: lineage(e.lineage) }),
				text: T('kronika.ev.language_emerged.text', { n }),
				details
			};
		}
		case 'language_split':
			add('kronika.term.language', lineage(e.lineage));
			add('kronika.term.parent', lineage(e.parent));
			return {
				title: T('kronika.ev.language_split.title', { language: lineage(e.lineage), parent: lineage(e.parent) }),
				text: '',
				details
			};
		case 'language_ended':
			add('kronika.term.language', lineage(e.lineage));
			return { title: T('kronika.ev.language_ended.title', { language: lineage(e.lineage) }), text: T('kronika.ev.language_ended.text'), details };
		case 'study_case':
			// studijní případ běhu: nadpis je štítek, druh události je v rozpisu karty
			add('kronika.term.event_kind', kindLabel(str(e.event_kind), tr));
			return { title: str(e.label) || kindLabel(kind, tr), text: '', details };
		default: {
			// neznámý druh: nadpis je jeho název, bez popisu
			const label = kindLabel(kind, tr);
			return { title: label, text: '', details };
		}
	}
}

function toEvent(e: RawEvent, index: number, source: Source, ctx: KronikaContext): KEvent {
	const { title, text, details } = describe(e.kind, e, ctx);
	const label = kindLabel(e.kind, ctx.tr);
	const T = (key: string) => ctx.tr(key as MessageKey);
	// studijní případ: zadání ho nese jako `study_case` (text), běh jako událost `study_case` s `label` a `spec_event`
	const isCase = source === 'author' ? isStudyCase(e) : e.kind === 'study_case';
	const caseLabel = source === 'author' ? caseLabelOf(e) : str(e.label);
	const specEvent = source === 'history' && e.kind === 'study_case' && typeof e.spec_event === 'number' ? e.spec_event : null;
	if (isCase && source === 'author') {
		if (caseLabel) details.unshift({ term: T('kronika.term.case'), value: caseLabel });
		details.push({ term: T('kronika.term.kind'), value: label });
	}
	return {
		key: `${source === 'author' ? 'a' : 'h'}${index}`,
		index,
		source,
		cls: isCase ? 'case' : classOf(source, e.kind),
		year: Math.round(Number(e.year)),
		kind: e.kind,
		kindLabel: label,
		title,
		text,
		details,
		caseLabel,
		specEvent,
		search: [label, caseLabel, title, text, ...details.map((d) => d.value)].join(' ').toLowerCase()
	};
}

/** Všechny události kroniky, od nejstarší. Drobné změny (SUMMARY_ONLY) se sem nedostanou. */
export function listEvents(worldEvents: RawEvent[], resultEvents: RawEvent[], ctx: KronikaContext): KEvent[] {
	const out: KEvent[] = [];
	worldEvents.forEach((e, index) => out.push(toEvent(e, index, 'author', ctx)));
	resultEvents.forEach((e, index) => {
		if (!SUMMARY_ONLY.has(e.kind)) out.push(toEvent(e, index, 'history', ctx));
	});
	return out.sort((a, b) => a.year - b.year || (a.source === b.source ? a.index - b.index : a.source === 'author' ? -1 : 1));
}

/** Filtr podle druhů (show) a hledání (query, bez ohledu na velikost písmen). */
export function filterEvents(events: KEvent[], filter: { show: Record<Cls, boolean>; query: string }): KEvent[] {
	const q = filter.query.trim().toLowerCase();
	return events.filter((e) => filter.show[e.cls] && (q === '' || e.search.includes(q)));
}

/**
 * Stejné události jednoho roku a druhu (dějiny autora i běhu) se sloučí do jednoho řádku s počtem;
 * studijní případ se nesloučí s obyčejnou událostí (jeho rámeček a odkaz by se ztratily).
 * Řádek nese popisek prvního člena; při počtu víc než jedna se popisek nahradí názvem druhu,
 * protože jeden člen by o celé skupině nic neřekl (jednotlivé události jsou ve Kartě vybrané události).
 */
export function mergeRows(events: KEvent[]): KRow[] {
	const rows = new Map<string, KRow>();
	for (const e of events) {
		const id = `${e.year}|${e.kind}|${e.cls === 'case'}`;
		const row = rows.get(id);
		if (row) {
			row.count += 1;
			row.members.push(e);
		} else {
			rows.set(id, { key: e.key, source: e.source, cls: e.cls, year: e.year, kind: e.kind, kindLabel: e.kindLabel, title: e.title, text: e.text, count: 1, members: [e] });
		}
	}
	for (const row of rows.values()) {
		if (row.count > 1) {
			row.title = row.kindLabel;
			row.text = '';
		}
	}
	return [...rows.values()];
}

/**
 * Století od začátku do konce běhu (včetně těch, kam zasahují události nebo souhrn).
 * Století je [k, k+99]; souhrn drobných změn je ve result.event_summary pod klíčem k.
 */
export function centuries(start: number, end: number, summary: Record<string, Record<string, number>> | undefined, rows: KRow[], tr: Tr): KCentury[] {
	const bucket = (y: number) => Math.floor(y / 100) * 100;
	const keys = [start, end, ...rows.map((r) => r.year), ...Object.keys(summary ?? {}).map(Number)].filter((y) => Number.isFinite(y));
	const lo = bucket(Math.min(...keys));
	const hi = bucket(Math.max(...keys));
	const out: KCentury[] = [];
	for (let k = lo; k <= hi; k += 100) {
		const counts = summary?.[String(k)] ?? {};
		const items = SUMMARY_ORDER.map((id) => ({
			id,
			value: SUMMARY_GROUPS[id].reduce((n, kind) => n + (counts[kind] ?? 0), 0)
		})).filter((s) => s.value > 0);
		const from = Math.max(k, Math.floor(start));
		out.push({
			key: k,
			from,
			to: Math.max(from, Math.min(k + 99, Math.floor(end))),
			summary: items,
			kinds: kindCounts(counts, tr),
			rows: rows.filter((r) => bucket(r.year) === k)
		});
	}
	return out;
}
