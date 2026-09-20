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

/** Geometry owned by the map editor. Coordinates are normalized percentages. */
export type MapGeometry =
	| { kind: 'point'; x: number; y: number }
	| { kind: 'line'; points: Array<{ x: number; y: number }> }
	| { kind: 'polygon'; points: Array<{ x: number; y: number }> };

export type WorldRegion = {
	id: EntityId;
	label: string;
	geometry: MapGeometry | null;
	interval: YearInterval;
	metadata: Record<string, unknown>;
};

export type WorldSettlement = {
	id: EntityId;
	label: string;
	geometry: Extract<MapGeometry, { kind: 'point' }>;
	regionId: EntityId | null;
	interval: YearInterval;
	metadata: Record<string, unknown>;
};

export type WorldRoute = {
	id: EntityId;
	label: string;
	geometry: Extract<MapGeometry, { kind: 'line' }> | null;
	interval: YearInterval;
	/** Optional relation link; the route itself never creates a relation. */
	relationId: EntityId | null;
	metadata: Record<string, unknown>;
};

export type PoliticalEntity = {
	id: EntityId;
	name: string;
	kind: 'state' | 'polity' | 'empire' | 'confederation' | 'other';
	geometry: Extract<MapGeometry, { kind: 'polygon' }> | null;
	interval: YearInterval;
	metadata: Record<string, unknown>;
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
	regions: WorldRegion[];
	settlements: WorldSettlement[];
	routes: WorldRoute[];
	politicalEntities: PoliticalEntity[];
	layers: Record<WorldLayerId, boolean>;
};

export const defaultWorldMapState = (): WorldMapState => ({
	document: { name: 'Prázdný svět', width: 2400, height: 1400 },
	points: [
		{ id: 'north-coast', label: 'Severní pobřeží', x: 24, y: 29, family: 'Asterická', languageId: 'asteric-coast', kind: 'language' },
		{ id: 'river-delta', label: 'Říční delta', x: 62, y: 52, family: 'Belarická', languageId: 'belaric-delta', kind: 'language' },
		{ id: 'island-west', label: 'Západní ostrovy', x: 80, y: 27, family: 'Norická', languageId: 'noric-west', kind: 'language' }
	],
	regions: [],
	settlements: [],
	routes: [],
	politicalEntities: [],
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

/** Errors raised by explicit genealogical edits.  Callers can show `message`
 * directly; no partial model is ever returned by an action. */
export class GenealogyValidationError extends Error {
	readonly code: 'missing-language' | 'duplicate-language' | 'invalid-interval' | 'invalid-parent' | 'cycle' | 'invalid-year';

	constructor(code: GenealogyValidationError['code'], message: string) {
		super(message);
		this.name = 'GenealogyValidationError';
		this.code = code;
	}
}

export type SplitLanguageInput = {
	parentId: EntityId;
	year: Year;
	children: Array<{
		id: EntityId;
		name: string;
		familyId?: EntityId | null;
		metadata?: Record<string, unknown>;
	}>;
};

export type EndLanguageInput = { languageId: EntityId; year: Year };

function copyModel(model: WorldModel): WorldModel {
	// structuredClone keeps metadata values such as arrays intact and prevents
	// an editor action from mutating the currently displayed model on failure.
	return structuredClone(model);
}

function validateInterval(intervalValue: YearInterval, label: string): void {
	if (!Number.isFinite(intervalValue.startYear) || (intervalValue.endYear !== null && !Number.isFinite(intervalValue.endYear))) {
		throw new GenealogyValidationError('invalid-interval', `${label} má neplatný časový interval.`);
	}
	if (intervalValue.endYear !== null && intervalValue.endYear < intervalValue.startYear) {
		throw new GenealogyValidationError('invalid-interval', `${label} končí před svým začátkem.`);
	}
}

/** Validates only genealogical entities; map geometry and presences are not touched. */
export function validateGenealogy(model: WorldModel): void {
	const byId = new Map<string, LanguageEntity>();
	for (const language of model.languages) {
		if (byId.has(language.id)) throw new GenealogyValidationError('duplicate-language', `Jazyk ${language.id} je uveden vícekrát.`);
		byId.set(language.id, language);
		validateInterval(language.interval, `Jazyk ${language.id}`);
		if (language.parentLanguageId === language.id) {
			throw new GenealogyValidationError('cycle', `Jazyk ${language.id} nemůže být vlastním rodičem.`);
		}
		if (language.parentLanguageId && !byId.has(language.parentLanguageId) && !model.languages.some((candidate) => candidate.id === language.parentLanguageId)) {
			throw new GenealogyValidationError('invalid-parent', `Rodič jazyka ${language.id} neexistuje.`);
		}
	}
	for (const language of model.languages) {
		if (language.parentLanguageId) {
			const parent = byId.get(language.parentLanguageId);
			if (!parent) throw new GenealogyValidationError('invalid-parent', `Rodič jazyka ${language.id} neexistuje.`);
			if (language.interval.startYear < parent.interval.startYear) {
				throw new GenealogyValidationError('invalid-year', `Jazyk ${language.id} vzniká před svým rodičem.`);
			}
			if (parent.interval.endYear !== null && language.interval.startYear > parent.interval.endYear) {
				throw new GenealogyValidationError('invalid-year', `Jazyk ${language.id} vzniká po zániku rodiče.`);
			}
		}
	}
	for (const language of model.languages) {
		const seen = new Set<string>();
		let current: string | null = language.id;
		while (current) {
			if (seen.has(current)) throw new GenealogyValidationError('cycle', `Genealogie obsahuje cyklus u jazyka ${language.id}.`);
			seen.add(current);
			current = byId.get(current)?.parentLanguageId ?? null;
		}
	}
	for (const relation of model.relations.filter((candidate) => candidate.kind === 'inherited')) {
		if (!byId.has(relation.sourceId) || !byId.has(relation.targetId)) {
			throw new GenealogyValidationError('invalid-parent', `Dědičný vztah ${relation.id} odkazuje na neexistující jazyk.`);
		}
	}
}

/** Return the selected language and all of its descendants, without editing the model. */
export function focusBranch(model: WorldModel, languageId: EntityId): EntityId[] {
	if (!model.languages.some((language) => language.id === languageId)) {
		throw new GenealogyValidationError('missing-language', `Jazyk ${languageId} neexistuje.`);
	}
	const descendants = new Set<EntityId>([languageId]);
	let changed = true;
	while (changed) {
		changed = false;
		for (const language of model.languages) {
			if (language.parentLanguageId && descendants.has(language.parentLanguageId) && !descendants.has(language.id)) {
				descendants.add(language.id);
				changed = true;
			}
		}
	}
	return [...descendants];
}

/** Split a language into children at a historical year. Geography is immutable. */
export function splitLanguage(model: WorldModel, input: SplitLanguageInput): WorldModel {
	validateGenealogy(model);
	const parent = model.languages.find((language) => language.id === input.parentId);
	if (!parent) throw new GenealogyValidationError('missing-language', `Jazyk ${input.parentId} neexistuje.`);
	if (!Number.isFinite(input.year) || input.year < parent.interval.startYear || (parent.interval.endYear !== null && input.year > parent.interval.endYear)) {
		throw new GenealogyValidationError('invalid-year', `Rozštěpení jazyka ${input.parentId} leží mimo jeho interval.`);
	}
	if (!input.children.length) throw new GenealogyValidationError('invalid-year', 'Rozštěpení musí vytvořit alespoň jeden jazyk.');
	const ids = new Set(model.languages.map((language) => language.id));
	for (const child of input.children) {
		if (!child.id || ids.has(child.id)) throw new GenealogyValidationError('duplicate-language', `Jazyk ${child.id || '(bez id)'} už existuje.`);
		ids.add(child.id);
	}
	const next = copyModel(model);
	const parentCopy = next.languages.find((language) => language.id === input.parentId)!;
	// The parent remains usable up to the split; an open interval is closed here.
	parentCopy.interval.endYear = input.year;
	parentCopy.status = input.year === parentCopy.interval.startYear ? 'dead' : parentCopy.status;
	for (const child of input.children) {
		next.languages.push({ id: child.id, name: child.name.trim() || child.id, familyId: child.familyId ?? parentCopy.familyId, parentLanguageId: parentCopy.id, interval: { startYear: input.year, endYear: null }, status: 'active', metadata: { ...(child.metadata ?? {}) } });
		next.relations.push({ id: `inherit-${parentCopy.id}-${child.id}-${input.year}`, kind: 'inherited', sourceId: parentCopy.id, targetId: child.id, interval: { startYear: input.year, endYear: null }, direction: 'ab', intensity: null, metadata: { reason: 'split' } });
	}
	next.events.push({ id: `split-${parentCopy.id}-${input.year}-${input.children.map((child) => child.id).join('-')}`, kind: 'split', interval: { startYear: input.year, endYear: input.year }, participantIds: [parentCopy.id, ...input.children.map((child) => child.id)], title: `Rozštěpení ${parentCopy.name}`, effects: { children: input.children.map((child) => child.id) }, metadata: {} });
	validateGenealogy(next);
	return next;
}

/** End a language without deleting it or changing any geographic presence. */
export function endLanguage(model: WorldModel, input: EndLanguageInput): WorldModel {
	validateGenealogy(model);
	const current = model.languages.find((language) => language.id === input.languageId);
	if (!current) throw new GenealogyValidationError('missing-language', `Jazyk ${input.languageId} neexistuje.`);
	if (!Number.isFinite(input.year) || input.year < current.interval.startYear || (current.interval.endYear !== null && input.year > current.interval.endYear)) {
		throw new GenealogyValidationError('invalid-year', `Konec jazyka ${input.languageId} leží mimo jeho interval.`);
	}
	const next = copyModel(model);
	const language = next.languages.find((candidate) => candidate.id === input.languageId)!;
	language.interval.endYear = input.year;
	language.status = 'dead';
	next.events.push({ id: `death-${language.id}-${input.year}`, kind: 'death', interval: { startYear: input.year, endYear: input.year }, participantIds: [language.id], title: `Zánik ${language.name}`, effects: {}, metadata: {} });
	validateGenealogy(next);
	return next;
}

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

function mapGeometry(value: unknown): MapGeometry | null {
	const raw = object(value);
	const kind = raw.kind;
	if (kind === 'point' && Number.isFinite(raw.x) && Number.isFinite(raw.y)) {
		return { kind: 'point', x: Number(raw.x), y: Number(raw.y) };
	}
	if (kind !== 'line' && kind !== 'polygon') return null;
	const points = Array.isArray(raw.points)
		? raw.points
			.filter((point): point is Record<string, unknown> => {
				const candidate = object(point);
				return Number.isFinite(candidate.x) && Number.isFinite(candidate.y);
			})
			.map((point) => ({ x: Number(point.x), y: Number(point.y) }))
		: [];
	return points.length >= (kind === 'polygon' ? 3 : 2) ? { kind, points } : null;
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

	const map = defaultWorldMapState();
	for (const presence of presences) {
		if (!presence.geometry) continue;
		const language = languages.find((candidate) => candidate.id === presence.languageId);
		if (!language) continue;
		map.points.push({
			id: presence.id,
			label: language.name,
			x: presence.geometry.x,
			y: presence.geometry.y,
			languageId: language.id,
			kind: 'language'
		});
	}

	for (const [index, raw] of (input.tradeRoutes ?? []).entries()) {
		const value = object(raw);
		const ids = Array.isArray(value.languageIds)
			? value.languageIds.filter((id): id is string => typeof id === 'string')
			: [];
		if (ids.length < 2) continue;
		for (let i = 1; i < ids.length; i += 1) {
			const startYear = numberOr(value.startYear, orderedYears[0] ?? 0);
			const endYear = nullableNumber(value.endYear);
			const routeId = stableId('route', raw, index);
			relations.push({
				id: `${routeId}-${i}`,
				kind: 'trade',
				sourceId: ids[0],
				targetId: ids[i],
				interval: interval(startYear, endYear),
				direction: 'both',
				intensity: nullableNumber(value.intensity),
				metadata: { ...value }
			});
		}
		map.routes.push({
			id: stableId('route', raw, index),
			label: text(value.label ?? value.name, `Trasa ${index + 1}`),
			geometry: mapGeometry(value.geometry) as WorldRoute['geometry'],
			interval: interval(numberOr(value.startYear, orderedYears[0] ?? 0), nullableNumber(value.endYear)),
			relationId: null,
			metadata: { ...value, languageIds: ids }
		});
	}

	for (const [index, raw] of (input.polities ?? []).entries()) {
		const value = object(raw);
		const candidateKind = text(value.kind, 'polity');
		const kind = ['state', 'polity', 'empire', 'confederation', 'other'].includes(candidateKind)
			? candidateKind as PoliticalEntity['kind']
			: 'other';
		map.politicalEntities.push({
			id: stableId('polity', raw, index),
			name: text(value.name ?? value.label, `Politický útvar ${index + 1}`),
			kind,
			geometry: mapGeometry(value.geometry) as PoliticalEntity['geometry'],
			interval: interval(numberOr(value.startYear, orderedYears[0] ?? 0), nullableNumber(value.endYear)),
			metadata: { ...value }
		});
	}

	return { schemaVersion: 1, languages, presences, relations, events, map };
}
