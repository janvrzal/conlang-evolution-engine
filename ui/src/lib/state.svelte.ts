/**
 * Stav projektu sdílený mezi Metaeditací a Mapou — a ukládaný na disk.
 *
 * Dřív to byl jen `$state` v paměti. Přechod mezi stránkami nebo F5 znamenal
 * ztrátu celé rozdělané práce, protože nikde nebyla žádná persistence.
 * Teď je zdrojem pravdy backend (`/api/projects/{id}`) a ukládá se automaticky.
 */
import { browser } from '$app/environment';
import { fetchProject, saveProject } from '$lib/api';
import { migrateLegacyWorldModel } from '$lib/world-model';
import type { WorldModel } from '$lib/world-model';

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

			projectState.simulationRunAt = data.simulationRunAt ?? null;
			projectState.simulationRunId = data.simulationRunId ?? null;
			projectState.mapBackground = data.mapBackground ?? null;
			projectState.schemaProfileId = data.schemaProfileId ?? 'heuristic-default';
			projectState.empiricalPhonology = data.empiricalPhonology ?? false;
			projectState.calibration = data.calibration ?? emptyData().calibration;
			projectState.polities = data.polities ?? [];
			projectState.tradeRoutes = data.tradeRoutes ?? [];
			projectState.historicalEvents = data.historicalEvents ?? [];
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
