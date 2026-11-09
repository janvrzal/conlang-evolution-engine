// Výpočty obrazovky Dějiny: pruhy kroniky, zvýraznění kraje, šipky, pole událostí ze schématu a to, co z události v běhu vzešlo.
import type { MapArrow } from '$lib/ds';
import type { EngineSchema } from '$lib/engine';
import type { EngineEvent, ExportV2 } from './export';

export interface WorldEvent {
	kind: string;
	year: number;
	[key: string]: unknown;
}

export type LaneId = 'states' | 'society' | 'people' | 'sounds';

export const LANE_KINDS: Record<LaneId, string[]> = {
	states: ['state', 'annexation', 'secession', 'collapse', 'border_policy', 'language_policy'],
	society: ['lingua_franca', 'standard', 'schools', 'revival', 'preserve'],
	people: ['settlement', 'elite', 'identity', 'immigration'],
	sounds: ['sound_shift']
};
export const LANE_IDS = Object.keys(LANE_KINDS) as LaneId[];

export function laneOf(kind: string): LaneId {
	return LANE_IDS.find((id) => LANE_KINDS[id].includes(kind)) ?? 'people';
}

/** Krok roku události. */
export const YEAR_STEP = 25;
export const snapYear = (year: number, min: number, max: number) => Math.min(max, Math.max(min, Math.round(year / YEAR_STEP) * YEAR_STEP));

/** Studijní případ: zadání ho zatím žádnou vlastností nenese; podporujeme nepovinné `study_case`. */
export const isStudyCase = (ev: WorldEvent) => ev.study_case === true || (typeof ev.study_case === 'string' && ev.study_case !== '');

// ---------- stát v daném roce podle událostí zadání ----------

export interface StateAt {
	id: string;
	name: string;
	regions: string[];
}

/** Státy v roce podle událostí zadání (vznik, odtržení, připojení, zánik); jen pro zvýraznění „celého státu“. */
export function statesAt(events: WorldEvent[], year: number): StateAt[] {
	const out = new Map<string, StateAt>();
	const strip = (regions: string[]) => {
		for (const s of out.values()) s.regions = s.regions.filter((r) => !regions.includes(r));
	};
	for (const e of [...events].sort((a, b) => a.year - b.year)) {
		if (e.year >= year) break;
		const regions = (e.regions as string[] | undefined) ?? [];
		if (e.kind === 'state' || e.kind === 'secession') {
			strip(regions);
			out.set(String(e.id), { id: String(e.id), name: String(e.name ?? e.id), regions: [...regions] });
		} else if (e.kind === 'annexation' && out.has(String(e.state))) {
			strip(regions);
			out.get(String(e.state))!.regions.push(...regions);
		} else if (e.kind === 'collapse') out.delete(String(e.state));
	}
	return [...out.values()];
}

/** Kraj z odkazu enginu („m12-03+m09-04-0“, „m05-02-v0“): nejdelší id kraje, kterým odkaz začíná. */
export function resolveRegion(ref: unknown, regionIds: Iterable<string>): string | null {
	if (typeof ref !== 'string') return null;
	let best: string | null = null;
	for (const id of regionIds) if (ref.startsWith(id) && (!best || id.length > best.length)) best = id;
	return best;
}

/** Kraje, které událost zasahuje (zvýraznění na mapě). `statesNow` = státy v roce události. */
export function highlightOf(ev: WorldEvent, regionIds: string[], statesNow: StateAt[]): string[] {
	const out = new Set<string>();
	const add = (value: unknown) => {
		const r = resolveRegion(value, regionIds);
		if (r) out.add(r);
	};
	for (const key of ['regions', 'subjects'] as const) for (const r of (ev[key] as string[] | undefined) ?? []) add(r);
	for (const key of ['to', 'seat', 'source', 'capital', 'from']) add(ev[key]);
	const ref = (ev.state ?? ev.of) as string | undefined;
	if (ref) {
		const state = statesNow.find((s) => s.id === ref);
		if (state) for (const r of state.regions) out.add(r);
		else add(ref);
	}
	return [...out];
}

/** Šipky osídlení, elity a lingua franca. */
export function arrowsOf(ev: WorldEvent, regionIds: string[]): MapArrow[] {
	if (ev.kind === 'settlement') return pair(resolveRegion(ev.from, regionIds), [resolveRegion(ev.to, regionIds)], false);
	if (ev.kind === 'elite') return pair(resolveRegion(ev.from, regionIds), [resolveRegion(ev.seat, regionIds)], false);
	if (ev.kind === 'lingua_franca') return pair(resolveRegion(ev.source, regionIds), ((ev.regions as string[] | undefined) ?? []).map((r) => resolveRegion(r, regionIds)), true);
	return [];
}
function pair(from: string | null, tos: (string | null)[], dashed: boolean): MapArrow[] {
	if (!from) return [];
	return tos.filter((to): to is string => !!to && to !== from).map((to) => ({ from, to, dashed }));
}

// ---------- pole události ze schématu ----------

export type FieldKind = 'level' | 'state' | 'region' | 'regions' | 'language' | 'number' | 'integer' | 'bool' | 'text';

export interface FieldSpec {
	name: string;
	kind: FieldKind;
	required: boolean;
	/** u `level`: možné hodnoty */
	levels?: string[];
	min?: number;
	max?: number;
	/** hodnota ve schématu (nebo default) */
	default?: unknown;
}

/** Který slovní seznam úrovní patří poli (klíč v `schema.levels`). */
const LEVEL_OF: Record<string, string> = {
	policy: 'policy_levels',
	border: 'border_levels',
	centralization: 'centralization_levels',
	identity: 'identity_loyalty',
	literacy: 'literacy_levels',
	coverage: 'schooling_levels',
	spread: 'lingua_franca_levels',
	strength: 'revival_levels'
};
const STATE_FIELDS = new Set(['state', 'of']);
const REGION_FIELDS = new Set(['from', 'to', 'seat', 'capital', 'source']);
const REGIONS_FIELDS = new Set(['regions', 'subjects']);
const LANGUAGE_FIELDS = new Set(['language']);

type Json = Record<string, unknown>;

function propType(prop: Json): string | undefined {
	if (typeof prop.type === 'string') return prop.type;
	const any = prop.anyOf as Json[] | undefined;
	return any?.map((p) => p.type).find((t) => typeof t === 'string' && t !== 'null') as string | undefined;
}
function propBounds(prop: Json): { min?: number; max?: number } {
	const any = ((prop.anyOf as Json[] | undefined) ?? []).find((p) => p.type === 'number' || p.type === 'integer') ?? prop;
	const min = (any.minimum ?? any.exclusiveMinimum) as number | undefined;
	const max = (any.maximum ?? any.exclusiveMaximum) as number | undefined;
	return { min, max };
}

/** Definice události daného druhu ve JSON schématu světa. */
export function eventDef(schema: EngineSchema | null, kind: string): Json | null {
	const defs = (schema?.json_schema as Json | undefined)?.$defs as Record<string, Json> | undefined;
	if (!defs) return null;
	for (const def of Object.values(defs)) {
		const k = ((def.properties as Json | undefined)?.kind as Json | undefined)?.const;
		if (k === kind) return def;
	}
	return null;
}

/** Pole události (bez roku a druhu) v pořadí schématu; bez schématu prázdný seznam. */
export function fieldsOf(schema: EngineSchema | null, kind: string): FieldSpec[] {
	const def = eventDef(schema, kind);
	if (!def) return [];
	const required = new Set((def.required as string[] | undefined) ?? []);
	const out: FieldSpec[] = [];
	for (const [name, raw] of Object.entries((def.properties as Record<string, Json>) ?? {})) {
		if (name === 'year' || name === 'kind') continue;
		const type = propType(raw);
		const spec: FieldSpec = { name, kind: 'text', required: required.has(name), default: raw.default, ...propBounds(raw) };
		if (STATE_FIELDS.has(name)) spec.kind = 'state';
		else if (REGION_FIELDS.has(name)) spec.kind = 'region';
		else if (REGIONS_FIELDS.has(name) || type === 'array') spec.kind = 'regions';
		else if (LANGUAGE_FIELDS.has(name)) spec.kind = 'language';
		else if (type === 'boolean') spec.kind = 'bool';
		else if (type === 'integer') spec.kind = 'integer';
		else if (type === 'number') spec.kind = 'number';
		else if (LEVEL_OF[name] && schema?.levels[LEVEL_OF[name]]) {
			spec.kind = 'level';
			spec.levels = schema.levels[LEVEL_OF[name]];
		}
		out.push(spec);
	}
	return out;
}

export interface NewEventContext {
	regions: string[];
	states: string[];
	languages: string[];
	/** text pro povinný popis hláskového posunu */
	label: string;
}

/** Nová událost: povinná pole vyplněná rozumnými výchozími hodnotami. */
export function defaultEvent(schema: EngineSchema | null, kind: string, year: number, ctx: NewEventContext): WorldEvent {
	const ev: WorldEvent = { kind, year };
	const first = ctx.regions[0] ?? '';
	const second = ctx.regions[1] ?? first;
	for (const f of fieldsOf(schema, kind)) {
		if (!f.required) continue;
		if (f.kind === 'state') ev[f.name] = ctx.states[0] ?? '';
		else if (f.kind === 'region') ev[f.name] = f.name === 'from' || f.name === 'source' ? first : second;
		else if (f.kind === 'regions') ev[f.name] = [first];
		else if (f.kind === 'language') ev[f.name] = ctx.languages[0] ?? '';
		else if (f.kind === 'level') ev[f.name] = f.default ?? f.levels?.[0] ?? '';
		else if (f.kind === 'number' || f.kind === 'integer') ev[f.name] = f.default ?? 1;
		else if (f.kind === 'bool') ev[f.name] = f.default ?? false;
		else if (f.name === 'label') ev[f.name] = ctx.label;
		else if (f.name === 'family') ev[f.name] = ctx.languages[0] ?? '';
		else ev[f.name] = `${kind}-${year}`;
	}
	return ev;
}

/** Místo pro novou událost: za poslední událost, která nezačíná později (zadání je řazené podle roku). */
export function insertIndex(events: WorldEvent[], year: number): number {
	let at = 0;
	events.forEach((e, i) => {
		if (e.year <= year) at = i + 1;
	});
	return at;
}

// ---------- co z události v běhu vzešlo ----------

export interface Outcome {
	/** druh události enginu */
	kind: string;
	year: number;
	n?: number;
	name?: string;
}

const ENGINE_KIND: Record<string, string> = { elite: 'conquest', settlement: 'migration', revival: 'revival_movement' };
const same = (a: unknown, b: unknown) => a != null && a === b;
const overlaps = (a: unknown, b: unknown) => Array.isArray(a) && Array.isArray(b) && a.some((x) => b.includes(x));
const count = (v: unknown) => (Array.isArray(v) ? v.length : undefined);

/** Události enginu, které odpovídají události zadání (stejný druh, blízký rok, stejný stát nebo kraj). */
export function outcomesOf(ev: WorldEvent, events: EngineEvent[], regionIds: string[]): Outcome[] {
	const kind = ENGINE_KIND[ev.kind] ?? ev.kind;
	const out: Outcome[] = [];
	for (const e of events) {
		if (e.kind !== kind || Math.abs(e.year - ev.year) > YEAR_STEP) continue;
		let match = false;
		let n: number | undefined;
		let name: string | undefined;
		switch (ev.kind) {
			case 'state':
				match = same(e.name, ev.name);
				n = count(e.regions);
				name = String(e.name ?? '');
				break;
			case 'secession':
			case 'collapse':
				match = same(e.state, ev.state ?? ev.id);
				n = count(e.regions);
				break;
			case 'annexation':
				match = same(e.state, ev.state);
				n = count(e.bilingual);
				break;
			case 'border_policy':
				match = same(e.state, ev.state);
				name = String(e.border ?? '');
				break;
			case 'standard':
				match = same(e.of, ev.of);
				n = count(e.readers);
				break;
			case 'schools':
				match = same(e.of, ev.of);
				n = count(e.pupils);
				break;
			case 'lingua_franca':
				match = overlaps(e.regions, ev.regions);
				n = count(e.bilingual);
				break;
			case 'identity':
			case 'revival':
				match = overlaps(e.regions, ev.regions);
				n = count(e.groups ?? e.speakers);
				break;
			case 'elite':
				match = Array.isArray(e.subjects) && e.subjects.some((s) => resolveRegion(String(s).replace(/^@/, ''), regionIds) === resolveRegion(ev.seat, regionIds));
				n = count(e.subjects);
				break;
			case 'settlement': {
				const sources = (e.sources as [string, number][] | undefined) ?? [];
				match = typeof e.target === 'string' && resolveRegion(e.target, regionIds) === resolveRegion(ev.to, regionIds) && sources.some(([s]) => resolveRegion(s, regionIds) === resolveRegion(ev.from, regionIds));
				n = sources.reduce((a, [, p]) => a + p, 0);
				break;
			}
		}
		if (match) out.push({ kind, year: e.year, n, name });
	}
	return out;
}

export interface LoanShare {
	region: string;
	words: number;
	total: number;
}

/** Podíl slov jazyka elity ve slovníku největší domácí skupiny kraje (koncový export). */
export function languageShare(result: ExportV2, region: string, language: string, regionOfVillage: (village: string) => string | undefined): LoanShare | null {
	const best = result.groups
		.filter((g) => g.domain === 'home' && !g.aggregate && regionOfVillage(g.id.split('>')[0]) === region)
		.sort((a, b) => b.population - a.population)[0];
	const lex = best ? result.lexicon[best.id] : undefined;
	if (!lex) return null;
	const entries = Object.values(lex);
	return { region, words: entries.filter((e) => e.language === language).length, total: entries.length };
}
