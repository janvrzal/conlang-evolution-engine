/**
 * Stav projektu sdílený mezi Metaeditací a Mapou — a ukládaný na disk.
 *
 * Dřív to byl jen `$state` v paměti. Přechod mezi stránkami nebo F5 znamenal
 * ztrátu celé rozdělané práce, protože nikde nebyla žádná persistence.
 * Teď je zdrojem pravdy backend (`/api/projects/{id}`) a ukládá se automaticky.
 */
import { browser } from '$app/environment';
import { fetchProject, saveProject } from '$lib/api';

/** Jak dlouho po poslední změně se čeká, než se uloží. */
const AUTOSAVE_DELAY_MS = 800;

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

export type ProjectData = {
	/** Vygenerovaný proto-slovník z Metaeditace. */
	generatedProtoLexicon: any[];
	/** Body na časové ose. */
	timeSteps: number[];
	/** Uzly a hrany pro každý rok na ose. */
	snapshots: Record<number, { nodes: any[]; edges: any[] }>;
	/** Nastavení protojazyků z Metaeditace. */
	protoLanguages: any[];
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
	return {
		generatedProtoLexicon: [],
		timeSteps: [0, 500, 1000, 1500],
		snapshots: { 0: { nodes: [protoNode(0)], edges: [] } },
		protoLanguages: []
	};
}

export const projectState = $state<{
	id: string | null;
	name: string;
	loaded: boolean;
	status: SaveStatus;
	error: string | null;
	lastSavedAt: string | null;
	/** Výsledek poslední simulace — přepočitatelný, na disk nepatří. */
	simulationResult: any | null;
	generatedProtoLexicon: any[];
	timeSteps: number[];
	snapshots: Record<number, { nodes: any[]; edges: any[] }>;
	protoLanguages: any[];
}>({
	id: null,
	name: 'Nový projekt',
	loaded: false,
	status: 'idle',
	error: null,
	lastSavedAt: null,
	simulationResult: null,
	...emptyData()
});

let saveTimer: ReturnType<typeof setTimeout> | null = null;
let saveInFlight = false;
let saveAgain = false;

/** Co se skutečně ukládá — bez odvoditelných a přechodných věcí. */
function snapshotData(): ProjectData {
	return {
		generatedProtoLexicon: $state.snapshot(projectState.generatedProtoLexicon) as any[],
		timeSteps: $state.snapshot(projectState.timeSteps) as number[],
		snapshots: $state.snapshot(projectState.snapshots) as ProjectData['snapshots'],
		protoLanguages: $state.snapshot(projectState.protoLanguages) as any[]
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
		projectState.simulationResult = null;
		projectState.loaded = false;
	}

	projectState.id = id;
	projectState.error = null;

	try {
		const project = await fetchProject(id);
		if (project) {
			projectState.name = project.name;
			const data = { ...emptyData(), ...(project.data as Partial<ProjectData>) };
			projectState.generatedProtoLexicon = data.generatedProtoLexicon;
			projectState.timeSteps = data.timeSteps;
			projectState.snapshots = ensureSeed(data.snapshots, data.timeSteps);
			projectState.protoLanguages = data.protoLanguages;
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
	} finally {
		projectState.loaded = true;
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
