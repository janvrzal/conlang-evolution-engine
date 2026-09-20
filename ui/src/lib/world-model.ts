/**
 * Canonical world model used by the new editors.
 *
 * The old map editor stores a rendered graph for every selected year.  That is
 * useful as a compatibility format, but it is not a good domain model: a
 * language, its location and a relationship are three different things.  The
 * types below keep those concerns separate and use intervals for temporal
 * state.  The legacy snapshots deliberately remain untouched in ProjectData.
 */

export type Year = number;
export type EntityId = string;

export type YearInterval = {
	startYear: Year;
	endYear: Year | null;
};

export type LanguageStatus = 'active' | 'dead' | 'unknown';

export type LanguageEntity = {
	id: EntityId;
	name: string;
	familyId: EntityId | null;
	parentLanguageId: EntityId | null;
	interval: YearInterval;
	status: LanguageStatus;
	/** Optional editor-facing metadata carried over from the legacy node. */
	metadata: Record<string, unknown>;
};

export type Presence = {
	id: EntityId;
	languageId: EntityId;
	regionId: EntityId | null;
	interval: YearInterval;
	/** Position is retained for a painless migration to the map editor. */
	geometry: { kind: 'point'; x: number; y: number } | null;
	speakerEstimate: number | null;
	status: 'primary' | 'secondary' | 'historical';
	metadata: Record<string, unknown>;
};

export type RelationKind =
	| 'inherited'
	| 'contact'
	| 'trade'
	| 'polity'
	| 'war'
	| 'migration'
	| 'religion'
	| 'elite'
	| 'other';

export type Relation = {
	id: EntityId;
	kind: RelationKind;
	sourceId: EntityId;
	targetId: EntityId;
	interval: YearInterval;
	/** Direction is intentionally free-form for old edge metadata. */
	direction: 'ab' | 'ba' | 'both' | 'unknown';
	intensity: number | null;
	metadata: Record<string, unknown>;
};

export type HistoricalEventKind =
	| 'split'
	| 'migration'
	| 'war'
	| 'contact'
	| 'standardization'
	| 'renaming'
	| 'death'
	| 'other';

export type HistoricalEvent = {
	id: EntityId;
	kind: HistoricalEventKind;
	interval: YearInterval;
	participantIds: EntityId[];
	title: string;
	effects: Record<string, unknown>;
	metadata: Record<string, unknown>;
};

export type WorldLayerId = 'languages' | 'regions' | 'settlements' | 'routes' | 'politics';

export type WorldMapPoint = {
	id: EntityId;
	label: string;
	x: number;
	y: number;
	family?: string;
	languageId?: EntityId;
	kind?: 'language' | 'settlement' | 'region';
};

/** Persistent geographic state. It is deliberately not part of genealogy. */
export type WorldMapState = {
	document: {
		name: string;
		width: number;
		height: number;
		/** A data URL keeps imported maps portable and survives a reload. */
		backgroundDataUrl?: string;
	};
	points: WorldMapPoint[];
	layers: Record<WorldLayerId, boolean>;
};

export const defaultWorldMapState = (): WorldMapState => ({
	document: { name: 'Prázdný svět', width: 2400, height: 1400 },
	points: [
		{ id: 'north-coast', label: 'Severní pobřeží', x: 24, y: 29, family: 'Asterická', languageId: 'asteric-coast', kind: 'language' },
		{ id: 'river-delta', label: 'Říční delta', x: 62, y: 52, family: 'Belarická', languageId: 'belaric-delta', kind: 'language' },
		{ id: 'island-west', label: 'Západní ostrovy', x: 80, y: 27, family: 'Norická', languageId: 'noric-west', kind: 'language' }
	],
	layers: { languages: true, regions: true, settlements: true, routes: false, politics: false }
});

export type WorldModel = {
	schemaVersion: 1;
	languages: LanguageEntity[];
	presences: Presence[];
	relations: Relation[];
	events: HistoricalEvent[];
	map: WorldMapState;
};

type LegacyNode = {
	id?: unknown;
	position?: { x?: unknown; y?: unknown };
	data?: Record<string, unknown>;
};

type LegacyEdge = {
	id?: unknown;
	source?: unknown;
	target?: unknown;
	type?: unknown;
	data?: Record<string, unknown>;
};

export type LegacySnapshot = { nodes?: LegacyNode[]; edges?: LegacyEdge[] };
export type LegacySnapshots = Record<string | number, LegacySnapshot>;

export type LegacyWorldInput = {
	snapshots?: LegacySnapshots | null;
	timeSteps?: number[] | null;
	historicalEvents?: unknown[] | null;
	polities?: unknown[] | null;
	tradeRoutes?: unknown[] | null;
};

function text(value: unknown, fallback: string): string {
	return typeof value === 'string' && value.trim() ? value : fallback;
}

function numberOr(value: unknown, fallback: number): number {
	return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function nullableNumber(value: unknown): number | null {
	return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function object(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

/** Stable identifier for imported records which did not have an id. */
function stableId(prefix: string, value: unknown, index: number): string {
	const explicit = object(value).id;
	if (typeof explicit === 'string' && explicit) return explicit;
	const raw = JSON.stringify(value) ?? '';
	let hash = 2166136261;
	for (let i = 0; i < raw.length; i += 1) {
		hash ^= raw.charCodeAt(i);
		hash = Math.imul(hash, 16777619);
	}
	return `${prefix}-${(hash >>> 0).toString(36)}-${index}`;
}

function interval(startYear: number, endYear: number | null = null): YearInterval {
	return { startYear, endYear: endYear !== null && endYear >= startYear ? endYear : null };
}

function relationKind(edge: LegacyEdge): RelationKind {
	const data = object(edge.data);
	const kind = text(data.contactType ?? data.kind, '');
	if (edge.type === 'contact') {
		if (kind === 'war' || kind === 'trade' || kind === 'religion' || kind === 'elite') return kind;
		return 'contact';
	}
	return 'inherited';
}

function eventKind(value: unknown): HistoricalEventKind {
	const kind = text(object(value).kind, 'other');
	if (['split', 'migration', 'war', 'contact', 'standardization', 'renaming', 'death'].includes(kind)) {
		return kind as HistoricalEventKind;
	}
	return 'other';
}

/**
 * Deterministically converts legacy per-year graph snapshots to entities and
 * intervals.  This is intentionally a pure function: loading the same old
 * project twice produces byte-for-byte equivalent model data.
 */
export function migrateLegacyWorldModel(input: LegacyWorldInput): WorldModel {
	const snapshots = input.snapshots ?? {};
	const years = Object.keys(snapshots)
		.map(Number)
		.filter(Number.isFinite)
		.sort((a, b) => a - b);
	const orderedYears = years.length ? years : [...(input.timeSteps ?? [])].sort((a, b) => a - b);
	const lastYear = orderedYears.at(-1) ?? 0;

	const nodeById = new Map<string, { node: LegacyNode; years: number[]; dead: boolean; deathYear: number | null }>();
	for (const year of orderedYears) {
		for (const node of snapshots[year]?.nodes ?? []) {
			const id = text(node.id, '');
			if (!id) continue;
			const current = nodeById.get(id) ?? { node, years: [], dead: false, deathYear: null };
			current.years.push(year);
			if (object(node.data).isDead === true) {
				current.dead = true;
				current.deathYear = current.deathYear === null ? year : Math.min(current.deathYear, year);
			}
			// Keep the first occurrence as the stable source of identity and name.
			nodeById.set(id, current);
		}
	}

	const languages: LanguageEntity[] = [];
	const presences: Presence[] = [];
	for (const [id, record] of [...nodeById.entries()].sort(([a], [b]) => a.localeCompare(b))) {
		const data = object(record.node.data);
		const firstYear = numberOr(data.year, Math.min(...record.years));
		const dead = record.dead || data.isDead === true;
		const deathYear = dead
			? numberOr(data.deathYear, record.deathYear ?? firstYear)
			: null;
		const parent = typeof data.parentLanguageId === 'string' ? data.parentLanguageId : null;
		const family = typeof data.familyId === 'string' ? data.familyId : null;
		languages.push({
			id,
			name: text(data.label ?? data.name, id),
			familyId: family,
			parentLanguageId: parent,
			interval: interval(firstYear, deathYear),
			status: dead ? 'dead' : 'active',
			metadata: { ...data }
		});

		const position = record.node.position;
		const geometry = position
			? { kind: 'point' as const, x: numberOr(position.x, 0), y: numberOr(position.y, 0) }
			: null;
		const lastPresenceYear = dead ? deathYear ?? Math.max(...record.years) : Math.max(...record.years);
		presences.push({
			id: `presence-${id}`,
			languageId: id,
			regionId: typeof data.regionId === 'string' ? data.regionId : null,
			interval: interval(firstYear, lastPresenceYear < lastYear ? lastPresenceYear : null),
			geometry,
			speakerEstimate: nullableNumber(data.speakerEstimate),
			status: 'primary',
			metadata: {}
		});
	}

	const edgeById = new Map<string, { edge: LegacyEdge; years: number[] }>();
	for (const year of orderedYears) {
		for (const edge of snapshots[year]?.edges ?? []) {
			const id = text(edge.id, '');
			const source = text(edge.source, '');
			const target = text(edge.target, '');
			if (!id || !source || !target) continue;
			const current = edgeById.get(id) ?? { edge, years: [] };
			current.years.push(year);
			edgeById.set(id, current);
		}
	}
	const relations: Relation[] = [...edgeById.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([id, record]) => {
		const data = object(record.edge.data);
		const firstYear = numberOr(data.year, Math.min(...record.years));
		const observedLast = Math.max(...record.years);
		const explicitEnd = nullableNumber(data.endYear);
		return {
			id,
			kind: relationKind(record.edge),
			sourceId: String(record.edge.source),
			targetId: String(record.edge.target),
			interval: interval(firstYear, explicitEnd ?? (observedLast < lastYear ? observedLast : null)),
			direction: data.direction === 'ab' || data.direction === 'ba' || data.direction === 'both' ? data.direction : 'unknown',
			intensity: nullableNumber(data.intensity),
			metadata: { ...data }
		};
	});

	const events: HistoricalEvent[] = (input.historicalEvents ?? []).map((raw, index) => {
		const value = object(raw);
		const startYear = numberOr(value.startYear, orderedYears[0] ?? 0);
		const duration = nullableNumber(value.duration);
		const explicitEnd = nullableNumber(value.endYear);
		const participants = Array.isArray(value.targetLanguageIds)
			? value.targetLanguageIds.filter((id): id is string => typeof id === 'string')
			: [];
		return {
			id: stableId('event', raw, index),
			kind: eventKind(raw),
			interval: interval(startYear, explicitEnd ?? (duration !== null ? startYear + duration : startYear)),
			participantIds: participants,
			title: text(value.endonym ?? value.exonym ?? value.kind, 'Historická událost'),
			effects: object(value.effects),
			metadata: { ...value }
		};
	});

	for (const [index, raw] of (input.tradeRoutes ?? []).entries()) {
		const value = object(raw);
		const ids = Array.isArray(value.languageIds)
			? value.languageIds.filter((id): id is string => typeof id === 'string')
			: [];
		if (ids.length < 2) continue;
		for (let i = 1; i < ids.length; i += 1) {
			const startYear = numberOr(value.startYear, orderedYears[0] ?? 0);
			const endYear = nullableNumber(value.endYear);
			relations.push({
				id: `${stableId('route', raw, index)}-${i}`,
				kind: 'trade',
				sourceId: ids[0],
				targetId: ids[i],
				interval: interval(startYear, endYear),
				direction: 'both',
				intensity: nullableNumber(value.intensity),
				metadata: { ...value }
			});
		}
	}

	return { schemaVersion: 1, languages, presences, relations, events, map: defaultWorldMapState() };
}
