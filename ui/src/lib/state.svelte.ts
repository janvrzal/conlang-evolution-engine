/**
 * Stav projektu sdílený mezi Metaeditací a Mapou — a ukládaný na disk.
 *
 * Dřív to byl jen `$state` v paměti. Přechod mezi stránkami nebo F5 znamenal
 * ztrátu celé rozdělané práce, protože nikde nebyla žádná persistence.
 * Teď je zdrojem pravdy backend (`/api/projects/{id}`) a ukládá se automaticky.
 */
import { browser } from '$app/environment';
import { fetchProject, saveProject } from '$lib/api';
import { defaultWorldMapState, endLanguage, migrateLegacyWorldModel, splitLanguage } from '$lib/world-model';
import { draftToHistoricalEvent, historicalEventToLegacy, validateHistoricalEvent, type HistoricalEventDraft } from '$lib/timeline-events';
import type {
	HistoricalEvent,
	PoliticalEntity,
	Presence,
	WorldMapState,
	WorldModel,
	WorldLayerId,
	WorldRegion,
	WorldRoute,
	WorldSettlement
} from '$lib/world-model';
import type { EndLanguageInput, SplitLanguageInput } from '$lib/world-model';

/** Jak dlouho po poslední změně se čeká, než se uloží. */
const AUTOSAVE_DELAY_MS = 800;

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

export type MapBackground = {
	/** Lokální data URL; projekt je bez externí URL reprodukovatelný i offline. */
	dataUrl: string;
	/** Měřítko vůči přirozené velikosti obrázku v procentech. */
	scale: number;
	/** Čitelnost uzlů nad podkladem. */
	opacity: number;
};

export type CalibrationSettings = {
	sound_changes_per_millennium: number;
	change_spread_years: number;
	isolation: number;
	replacement_rate: number;
	loss_rate: number;
	homophony_resolution_rate: number;
};

export type HomophonyStrategy =
	| { kind: 'colexification' }
	| { kind: 'semantic_shift'; source: string }
	| { kind: 'derivation'; root: string; affix: string; prefix?: boolean }
	| { kind: 'compound'; head: string; modifier: string };

export type HomophonyQueueDecision =
	| 'reviewing'
	| 'dismissed'
	| { status: 'resolved'; year: number; strategy: HomophonyStrategy; loserConcept: string };

export type ProjectData = {
	/** Canonical entity/interval model; legacy snapshots remain for compatibility. */
	worldModel: WorldModel;
	polities: any[];
	tradeRoutes: any[];
	historicalEvents: any[];
	/** Vygenerovaný proto-slovník z Metaeditace. */
	generatedProtoLexicon: any[];
	/** Rozsah výchozí slovní zásoby: malé kurátorované jádro nebo celý korpus. */
	vocabularyProfile: 'core' | 'full';
	/** Významy specifické pro daný svět, přidávané při nové generaci. */
	customConcepts: string;
	/** Autorský stav položek fronty homofonií mezi načteními projektu. */
	homophonyQueue: Record<string, HomophonyQueueDecision>;
	/** Body na časové ose. */
	timeSteps: number[];
	/** Uzly a hrany pro každý rok na ose. */
	snapshots: Record<number, { nodes: any[]; edges: any[] }>;
	/** Nastavení protojazyků z Metaeditace. */
	protoLanguages: any[];
	/**
	 * Poslední vygenerované jazyky.
	 *
	 * Přepočitatelné to sice je, ale je to hlavní výstup aplikace — po F5 by
	 * jinak zmizely vygenerované jazyky i tlačítko na jejich zobrazení.
	 */
	/** Kdy simulace proběhla, ať je poznat, jak je výsledek starý. */
	simulationRunAt: string | null;
	/** Identifikátor uložené genealogie; stabilní mezi otevřeními projektu. */
	simulationRunId: string | null;
	/** Volitelný rastrový podklad mapového editoru. */
	mapBackground: MapBackground | null;
	/** Volba vah generátoru; ID pochází z bezpečného seznamu backendu. */
	schemaProfileId: string;
	/** PHOIBLE je lokální filtr; bez cache backend bezpečně pokračuje bez něj. */
	empiricalPhonology: boolean;
	calibration: CalibrationSettings;
};

/** Uzel, kterým každý nový projekt začíná. */
function protoNode(year: number) {
	return {
		id: 'lang-1',
		type: 'language',
		position: { x: 400, y: 100 },
		data: { label: 'Protojazyk', isProto: true, year }
	};
}

function emptyData(): ProjectData {
	// Protojazyk je součástí prázdného projektu, ne něco, co se doplní později.
	// Když se sázel až po doběhnutí loadProject(), stihl ho přebít
	// synchronizační efekt v mapě a do projektu se uložil prázdný snapshot.
	const timeSteps = [0, 500, 1000, 1500];
	const snapshots = { 0: { nodes: [protoNode(0)], edges: [] } };
	return {
		worldModel: migrateLegacyWorldModel({ snapshots, timeSteps }),
		polities: [],
		tradeRoutes: [],
		historicalEvents: [],
		generatedProtoLexicon: [],
		vocabularyProfile: 'core',
		customConcepts: '',
		homophonyQueue: {},
		timeSteps,
		snapshots,
		protoLanguages: [],
		simulationRunAt: null,
		simulationRunId: null,
		mapBackground: null,
		schemaProfileId: 'heuristic-default',
		empiricalPhonology: false,
		calibration: {
			sound_changes_per_millennium: 8,
			change_spread_years: 120,
			isolation: 0.5,
			replacement_rate: 0.01,
			loss_rate: 0.005,
			homophony_resolution_rate: 0.3
		}
	};
}

function normalizeWorldMap(value: unknown): WorldMapState {
	const fallback = defaultWorldMapState();
	if (!value || typeof value !== 'object') return fallback;
	const raw = value as Partial<WorldMapState>;
	const document = raw.document && typeof raw.document === 'object'
		? { ...fallback.document, ...(raw.document as WorldMapState['document']) }
		: fallback.document;
	const layers = { ...fallback.layers, ...(raw.layers && typeof raw.layers === 'object' ? raw.layers : {}) };
	const points = Array.isArray(raw.points) ? raw.points : fallback.points;
	const regions = Array.isArray(raw.regions) ? raw.regions : fallback.regions;
	const settlements = Array.isArray(raw.settlements) ? raw.settlements : fallback.settlements;
	const routes = Array.isArray(raw.routes) ? raw.routes : fallback.routes;
	const politicalEntities = Array.isArray(raw.politicalEntities) ? raw.politicalEntities : fallback.politicalEntities;
	return { document, layers, points, regions, settlements, routes, politicalEntities };
}

export const projectState = $state<{
	id: string | null;
	name: string;
	loaded: boolean;
	status: SaveStatus;
	error: string | null;
	lastSavedAt: string | null;
	simulationRunAt: string | null;
	simulationRunId: string | null;
	mapBackground: MapBackground | null;
	schemaProfileId: string;
	empiricalPhonology: boolean;
	calibration: CalibrationSettings;
	polities: any[];
	tradeRoutes: any[];
	historicalEvents: any[];
	generatedProtoLexicon: any[];
	vocabularyProfile: 'core' | 'full';
	customConcepts: string;
	homophonyQueue: Record<string, HomophonyQueueDecision>;
	timeSteps: number[];
	snapshots: Record<number, { nodes: any[]; edges: any[] }>;
	protoLanguages: any[];
	worldModel: WorldModel;
}>({
	id: null,
	name: 'Nový projekt',
	loaded: false,
	status: 'idle',
	error: null,
	lastSavedAt: null,
	...emptyData()
});

let saveTimer: ReturnType<typeof setTimeout> | null = null;
let saveInFlight = false;
let saveAgain = false;

/** Co se skutečně ukládá — bez odvoditelných a přechodných věcí. */
function snapshotData(): ProjectData {
	return {
		worldModel: $state.snapshot(projectState.worldModel) as WorldModel,
		polities: $state.snapshot(projectState.polities) as any[],
		tradeRoutes: $state.snapshot(projectState.tradeRoutes) as any[],
		historicalEvents: $state.snapshot(projectState.historicalEvents) as any[],
		generatedProtoLexicon: $state.snapshot(projectState.generatedProtoLexicon) as any[],
		vocabularyProfile: projectState.vocabularyProfile,
		customConcepts: projectState.customConcepts,
		homophonyQueue: $state.snapshot(projectState.homophonyQueue) as Record<
			string,
			HomophonyQueueDecision
		>,
		timeSteps: $state.snapshot(projectState.timeSteps) as number[],
		snapshots: $state.snapshot(projectState.snapshots) as ProjectData['snapshots'],
		protoLanguages: $state.snapshot(projectState.protoLanguages) as any[],
		simulationRunAt: projectState.simulationRunAt,
		simulationRunId: projectState.simulationRunId,
		mapBackground: $state.snapshot(projectState.mapBackground) as MapBackground | null,
		schemaProfileId: projectState.schemaProfileId,
		empiricalPhonology: projectState.empiricalPhonology,
		calibration: $state.snapshot(projectState.calibration) as CalibrationSettings
	};
}

/**
 * Zaručí, že projekt má aspoň jeden uzel v prvním roce osy.
 * Chrání starší projekty uložené dřív, než se protojazyk stal součástí
 * prázdného stavu.
 */
function ensureSeed(
	snapshots: ProjectData['snapshots'],
	timeSteps: number[]
): ProjectData['snapshots'] {
	const first = timeSteps[0] ?? 0;
	const prazdny =
		!snapshots ||
		Object.keys(snapshots).length === 0 ||
		Object.values(snapshots).every((s) => !s?.nodes?.length);

	if (prazdny) {
		return { [first]: { nodes: [protoNode(first)], edges: [] } };
	}
	return snapshots;
}

export async function loadProject(id: string): Promise<void> {
	if (!browser) return;

	// Přepnutí na jiný projekt nesmí do nového nasypat data z předchozího.
	if (projectState.id !== id) {
		Object.assign(projectState, emptyData());
		projectState.loaded = false;
	}

	projectState.id = id;
	projectState.error = null;
	// Dokud odpověď opravdu nepřijde, nesmí žádný reaktivní efekt uložit
	// výchozí hodnoty přes existující projekt (typicky právě po restartu API).
	projectState.loaded = false;

	try {
		const project = await fetchProject(id);
		if (project) {
			projectState.name = project.name;
			const data = { ...emptyData(), ...(project.data as Partial<ProjectData>) };
			projectState.generatedProtoLexicon = data.generatedProtoLexicon;
			projectState.vocabularyProfile = data.vocabularyProfile ?? 'core';
			projectState.customConcepts = data.customConcepts ?? '';
			projectState.homophonyQueue = data.homophonyQueue ?? {};
			projectState.timeSteps = data.timeSteps;
			projectState.snapshots = ensureSeed(data.snapshots, data.timeSteps);
			projectState.protoLanguages = data.protoLanguages;
			projectState.worldModel =
				data.worldModel ??
				migrateLegacyWorldModel({
					snapshots: projectState.snapshots,
					timeSteps: data.timeSteps,
					historicalEvents: data.historicalEvents,
					polities: data.polities,
					tradeRoutes: data.tradeRoutes
				});
			projectState.worldModel.map = normalizeWorldMap(projectState.worldModel.map);

			projectState.simulationRunAt = data.simulationRunAt ?? null;
			projectState.simulationRunId = data.simulationRunId ?? null;
			projectState.mapBackground = data.mapBackground ?? null;
			projectState.schemaProfileId = data.schemaProfileId ?? 'heuristic-default';
			projectState.empiricalPhonology = data.empiricalPhonology ?? false;
			projectState.calibration = data.calibration ?? emptyData().calibration;
			projectState.polities = data.polities ?? [];
			projectState.tradeRoutes = data.tradeRoutes ?? [];
			projectState.historicalEvents = data.historicalEvents ?? [];
			// The interval model is canonical. Older projects may only have the
			// legacy list; migration has already populated events in that case.
			if (!projectState.worldModel.events.length && projectState.historicalEvents.length) {
				projectState.worldModel.events = migrateLegacyWorldModel({
					snapshots: projectState.snapshots,
					timeSteps: projectState.timeSteps,
					historicalEvents: projectState.historicalEvents
				}).events;
			}
			projectState.lastSavedAt = project.updated_at;
			projectState.status = 'saved';
		} else {
			// Ještě neexistuje — založíme ho hned, ať má uživatel co ukládat.
			projectState.status = 'idle';
			await flushSave();
		}
	} catch (e) {
		projectState.status = 'error';
		projectState.error = e instanceof Error ? e.message : String(e);
		return;
	} finally {
		// Jen úspěšné načtení (nebo úspěšné založení nového projektu) odemkne
		// autosave. V catch se returnem se finally provede také, proto stav
		// nastavujeme podmíněně podle chybového statusu.
		if (projectState.status !== 'error') {
			projectState.loaded = true;
		}
	}
}

/** Update persistent map state without touching languages or genealogical relations. */
export function updateWorldMap(patch: Partial<Omit<WorldMapState, 'layers'>> & { layers?: Partial<WorldMapState['layers']> }): void {
	const current = projectState.worldModel.map ?? defaultWorldMapState();
	projectState.worldModel.map = {
		...current,
		...patch,
		document: { ...current.document, ...(patch.document ?? {}) },
		layers: { ...current.layers, ...(patch.layers ?? {}) }
	};
	scheduleSave();
}

export function setWorldMapLayer(layer: WorldLayerId, visible: boolean): void {
	const current = projectState.worldModel.map ?? defaultWorldMapState();
	updateWorldMap({ layers: { ...current.layers, [layer]: visible } });
}

/** Timeline write boundary: events only; no map or genealogy side effects. */
export function upsertHistoricalEvent(
	draft: HistoricalEventDraft
): { ok: true; event: HistoricalEvent } | { ok: false; errors: string[] } {
	const knownLanguageIds = new Set(projectState.worldModel.languages.map((language) => language.id));
	const validation = validateHistoricalEvent(draft, knownLanguageIds);
	if (!validation.valid) return { ok: false, errors: validation.errors };
	const id = draft.id?.trim() || `event-${Date.now().toString(36)}`;
	const event = draftToHistoricalEvent(draft, id);
	const index = projectState.worldModel.events.findIndex((candidate) => candidate.id === id);
	if (index >= 0) projectState.worldModel.events[index] = event;
	else projectState.worldModel.events = [...projectState.worldModel.events, event];
	projectState.historicalEvents = projectState.worldModel.events.map(historicalEventToLegacy);
	scheduleSave();
	return { ok: true, event };
}

export function removeHistoricalEvent(id: string): void {
	projectState.worldModel.events = projectState.worldModel.events.filter((event) => event.id !== id);
	projectState.historicalEvents = projectState.worldModel.events.map(historicalEventToLegacy);
	scheduleSave();
}

/**
 * Map-only write: moving a presence changes geography, never language
 * identity, parentage, relations or historical events.
 */
export function updateWorldPresence(
	presenceId: string,
	patch: Partial<Pick<Presence, 'regionId' | 'geometry' | 'speakerEstimate' | 'status' | 'interval'>>
): void {
	const presence = projectState.worldModel.presences.find((item) => item.id === presenceId);
	if (!presence) return;
	Object.assign(presence, patch);
	scheduleSave();
}

function updateMapCollection<T extends { id: string }>(
	key: 'regions' | 'settlements' | 'routes' | 'politicalEntities',
	item: T
): void {
	const map = projectState.worldModel.map ?? defaultWorldMapState();
	const collection = map[key] as unknown as T[];
	const index = collection.findIndex((candidate) => candidate.id === item.id);
	if (index === -1) collection.push(item);
	else collection[index] = item;
	projectState.worldModel.map = { ...map, [key]: collection };
	scheduleSave();
}

/** Upsert map-owned geometry; none of these actions touch genealogy. */
export function upsertWorldRegion(region: WorldRegion): void {
	updateMapCollection('regions', region);
}

export function upsertWorldSettlement(settlement: WorldSettlement): void {
	updateMapCollection('settlements', settlement);
}

export function upsertWorldRoute(route: WorldRoute): void {
	updateMapCollection('routes', route);
}

export function upsertPoliticalEntity(entity: PoliticalEntity): void {
	updateMapCollection('politicalEntities', entity);
}

export function removeWorldMapEntity(
	key: 'regions' | 'settlements' | 'routes' | 'politicalEntities',
	id: string
): void {
	const map = projectState.worldModel.map ?? defaultWorldMapState();
	projectState.worldModel.map = {
		...map,
		[key]: (map[key] as Array<{ id: string }>).filter((item) => item.id !== id)
	};
	scheduleSave();
}

export function clearWorldMapBackground(): void {
	const current = projectState.worldModel.map ?? defaultWorldMapState();
	const { backgroundDataUrl: _removed, ...document } = current.document;
	updateWorldMap({ document });
}

function updateLegacyGenealogy(action: 'split' | 'end', payload: SplitLanguageInput | EndLanguageInput): void {
	// Snapshots are only a compatibility projection for the old canvas. These
	// edits intentionally never copy or move map geometry.
	const years = Object.keys(projectState.snapshots).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
	const year = payload.year;
	const affectedYears = years.filter((candidate) => candidate >= year);
	if (!affectedYears.includes(year)) affectedYears.push(year);
	for (const candidateYear of affectedYears.sort((a, b) => a - b)) {
		const source = projectState.snapshots[candidateYear] ?? { nodes: [], edges: [] };
		const nodes = source.nodes.map((node) => ({ ...node, data: node.data ? { ...node.data } : {} }));
		const edges = source.edges.map((edge) => ({ ...edge, data: edge.data ? { ...edge.data } : {} }));
		if (action === 'split') {
			const split = payload as SplitLanguageInput;
			for (const child of split.children) {
				if (!nodes.some((node) => node.id === child.id)) nodes.push({ id: child.id, type: 'language', position: { x: 0, y: 0 }, data: { label: child.name || child.id, year, parentLanguageId: split.parentId } });
				const edgeId = `inherit-${split.parentId}-${child.id}-${year}`;
				if (!edges.some((edge) => edge.id === edgeId)) edges.push({ id: edgeId, source: split.parentId, target: child.id, data: { year, relation: 'inheritance' } });
			}
		} else {
			const end = payload as EndLanguageInput;
			const node = nodes.find((candidate) => candidate.id === end.languageId);
			if (node) node.data = { ...(node.data ?? {}), isDead: true, deathYear: year };
		}
		projectState.snapshots[candidateYear] = { nodes, edges };
	}
}

/** Apply an explicit genealogical split and persist both modern and legacy views. */
export function splitProjectLanguage(input: SplitLanguageInput): void {
	projectState.worldModel = splitLanguage(projectState.worldModel, input);
	updateLegacyGenealogy('split', input);
	scheduleSave();
}

/** End a language while retaining its history and all geographic presences. */
export function endProjectLanguage(input: EndLanguageInput): void {
	projectState.worldModel = endLanguage(projectState.worldModel, input);
	updateLegacyGenealogy('end', input);
	scheduleSave();
}

/** Uloží okamžitě, bez čekání na debounce. */
export async function flushSave(): Promise<void> {
	if (!browser || !projectState.id) return;

	if (saveInFlight) {
		saveAgain = true;
		return;
	}

	saveInFlight = true;
	projectState.status = 'saving';
	try {
		const saved = await saveProject(projectState.id, {
			name: projectState.name,
			data: snapshotData() as unknown as Record<string, unknown>
		});
		projectState.lastSavedAt = saved.updated_at;
		projectState.status = 'saved';
		projectState.error = null;
	} catch (e) {
		projectState.status = 'error';
		projectState.error = e instanceof Error ? e.message : String(e);
	} finally {
		saveInFlight = false;
		if (saveAgain) {
			saveAgain = false;
			void flushSave();
		}
	}
}

/** Naplánuje uložení. Volá se po každé změně, kterou chceme udržet. */
export function scheduleSave(): void {
	if (!browser || !projectState.id || !projectState.loaded) return;

	projectState.status = 'dirty';
	if (saveTimer) clearTimeout(saveTimer);
	saveTimer = setTimeout(() => {
		saveTimer = null;
		void flushSave();
	}, AUTOSAVE_DELAY_MS);
}
