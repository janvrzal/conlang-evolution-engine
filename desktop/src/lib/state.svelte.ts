// Stav aplikace: otevřený svět (popis cee-v2-world/1), spojení s enginem, běh a výběr ve Výsledku.
import { API_REVISION, Engine, EngineError, connect, type EngineSchema, type Health, type Issue, type RunStatus, type StoredRun } from './engine';
import { baseName, forgetRecent, inApp, openProject, pickOpen, pickSave, recentProjects, saveProject, type RecentProject } from './files';
import type { ExportV2, FrameV2 } from './model/export';

export interface WorldSpec {
	format: 'cee-v2-world/1';
	name?: string;
	seed?: number;
	start_year?: number;
	end_year: number;
	background?: string;
	generation_years?: number;
	village_spacing?: number;
	semantics?: boolean;
	vocabulary?: number;
	languages: {
		id: string;
		name?: string;
		consonants?: string[];
		vowels?: string[];
		tones?: string[];
		syllables?: string | null;
		grammar?: string;
		stress?: string;
		words?: Record<string, string>;
		endonym?: string[];
		[key: string]: unknown;
	}[];
	regions: {
		id: string;
		name?: string;
		position: [number, number];
		neighbours?: string[];
		villages?: number;
		density?: number;
		language?: string;
		terrain?: string;
		identity?: string;
		city?: number | null;
		prestige?: number;
		[key: string]: unknown;
	}[];
	events: { kind: string; year: number; [key: string]: unknown }[];
	/** přepisy parametrů enginu: číslo, nebo celá tabulka u slovních úrovní */
	parameters?: Record<string, unknown>;
	[key: string]: unknown;
}

type EngineState = { phase: 'connecting' } | { phase: 'offline' } | { phase: 'outdated'; health: Health } | { phase: 'ready'; health: Health };

/** Výběr sdílený obrazovkami Výsledku (Atlas, Jazyky, Slova, Kronika, Co kdyby) a Dějin. */
export interface View {
	/** rok na časové ose; null = konec běhu */
	year: number | null;
	region: string | null;
	lineage: string | null;
	concept: string;
	/** index události v world.events */
	event: number | null;
	/** ukázat všechny jazyky, jak je počítá engine (jinak malé jazyky jako variety) */
	allLanguages: boolean;
}

/** Slovník v čase ve vzorku dat (vývoj v prohlížeči): rok → jazyk → slovník. */
type FixtureLexicon = { year: number; languages: Record<string, { group: string; forms: Record<string, string> }> }[];

/** Druhá větev pro „Co kdyby“: upravené zadání a jeho běh. */
export interface Branch {
	label: string;
	world: WorldSpec;
	run: RunStatus | null;
	frames: FrameV2[];
	result: ExportV2 | null;
}

/** Žádost o potvrzení (vykreslí ji kostra dialogem z ds). */
export interface ConfirmRequest {
	title: string;
	message: string;
	confirm: string;
	cancel: string;
	/** potvrzení něco zahodí (červené tlačítko) */
	danger?: boolean;
	resolve: (ok: boolean) => void;
}

interface Snapshot {
	world: WorldSpec;
	label: string;
}

const HISTORY = 100;

class App {
	world = $state<WorldSpec | null>(null);
	fileName = $state<string | null>(null);
	/** cesta k projektu na disku (jen v aplikaci) */
	filePath = $state<string | null>(null);
	/** nedávné projekty (jen v aplikaci) */
	recent = $state<RecentProject[]>([]);
	/** otevřená žádost o potvrzení */
	confirmRequest = $state<ConfirmRequest | null>(null);
	/** hlášení o souborech (uloženo, chyba) pro patu */
	notice = $state<string | null>(null);
	dirty = $state(false);
	engineState = $state<EngineState>({ phase: 'connecting' });
	issues = $state<Issue[] | null>(null);
	checking = $state(false);
	run = $state<RunStatus | null>(null);
	frames = $state.raw<FrameV2[]>([]);
	result = $state.raw<ExportV2 | null>(null);
	error = $state<string | null>(null);
	/** schéma enginu (úrovně, parametry, druhy událostí, slovníky); null bez enginu */
	schema = $state.raw<EngineSchema | null>(null);
	view = $state<View>({ year: null, region: null, lineage: null, concept: 'water', event: null, allLanguages: false });
	/** větev B pro Co kdyby (A je hlavní běh) */
	branch = $state.raw<Branch | null>(null);
	/** složka běhů projektu a uložené běhy (nejnovější první; jen v aplikaci) */
	runsDir = $state<string | null>(null);
	storedRuns = $state<StoredRun[]>([]);
	/** slovník v čase ze vzorku dat podle id běhu (jen vývoj v prohlížeči) */
	private fixtureLexicon = new Map<string, FixtureLexicon>();
	/** zadání, ze kterého je poslední výsledek (JSON) */
	private ranSpec = $state<string | null>(null);
	private undoStack = $state.raw<Snapshot[]>([]);
	private redoStack = $state.raw<Snapshot[]>([]);
	/** poslední úprava, kterou jde vrátit (pro hlášku „Vrátit“) */
	lastEdit = $state<string | null>(null);
	private engine: Engine | null = null;
	private polling: ReturnType<typeof setTimeout> | null = null;
	private checkTimer: ReturnType<typeof setTimeout> | null = null;

	/** Zadání se od posledního běhu změnilo. */
	get stale(): boolean {
		return !!this.world && this.ranSpec != null && JSON.stringify(this.world) !== this.ranSpec;
	}
	get running(): boolean {
		return this.run?.status === 'running';
	}
	get canUndo(): boolean {
		return this.undoStack.length > 0;
	}
	get canRedo(): boolean {
		return this.redoStack.length > 0;
	}
	get errors(): Issue[] {
		return (this.issues ?? []).filter((i) => i.severity !== 'warning');
	}
	get warnings(): Issue[] {
		return (this.issues ?? []).filter((i) => i.severity === 'warning');
	}

	async connect() {
		this.engineState = { phase: 'connecting' };
		const found = await connect();
		if (!found) {
			this.engineState = { phase: 'offline' };
			return;
		}
		this.engine = new Engine(found.base);
		this.engineState =
			found.health.api_revision < API_REVISION || found.health.v2_binding_fresh === false
				? { phase: 'outdated', health: found.health }
				: { phase: 'ready', health: found.health };
		this.schema = await this.engine.schema().catch(() => this.schema);
		if (this.world) await this.check();
		await this.refreshRecent();
	}

	load(world: WorldSpec, fileName: string | null, filePath: string | null = null) {
		this.world = world;
		this.fileName = fileName;
		this.filePath = filePath;
		this.dirty = false;
		this.result = null;
		this.run = null;
		this.frames = [];
		this.ranSpec = null;
		this.undoStack = [];
		this.redoStack = [];
		this.lastEdit = null;
		this.branch = null;
		this.storedRuns = [];
		this.view = { year: null, region: null, lineage: null, concept: 'water', event: null, allLanguages: false };
		void this.check();
	}

	async loadStarter() {
		const response = await fetch('/projects/talvera.cee.json');
		this.load(await response.json(), 'talvera.cee.json');
	}

	/** Potvrzení akce dialogem v kostře; vrátí true, když uživatel potvrdí. */
	confirm(options: Omit<ConfirmRequest, 'resolve'>): Promise<boolean> {
		return new Promise((resolve) => {
			this.confirmRequest = {
				...options,
				resolve: (ok) => {
					this.confirmRequest = null;
					resolve(ok);
				}
			};
		});
	}

	/** Neuložené změny: zeptá se, jestli je zahodit. Bez změn rovnou true. */
	async discardChanges(texts: { title: string; message: string; confirm: string; cancel: string }): Promise<boolean> {
		if (!this.dirty) return true;
		return this.confirm({ ...texts, danger: true });
	}

	async refreshRecent() {
		if (inApp()) this.recent = await recentProjects().catch(() => []);
	}

	/** Otevře projekt z disku a načte poslední hotový běh (přednostně ten, který sedí k zadání). */
	async openPath(path: string) {
		const opened = await openProject(path);
		this.load(opened.world, baseName(path), opened.path);
		this.runsDir = opened.runs.dir;
		this.storedRuns = opened.runs.runs;
		const done = opened.runs.runs.filter((r) => r.status === 'done' && r.has_result && !r.parent);
		const pick = done.find((r) => r.matches) ?? done[0];
		if (pick) await this.openRun(pick);
		await this.refreshRecent();
	}

	/** Načte uložený běh (snímky a výsledek) jako hlavní běh A. */
	async openRun(run: StoredRun) {
		if (!this.engine) return;
		if (this.polling) clearTimeout(this.polling);
		const status = await this.engine.status(run.path, 0);
		this.frames = status.frames;
		this.result = run.has_result ? await this.engine.result(run.path) : null;
		this.run = { ...status, frames: [] };
		// stale: běh z jiného zadání se ukáže jako zastaralý
		this.ranSpec = run.matches && this.world ? JSON.stringify(this.world) : `run:${run.id}`;
		this.view.year = null;
	}

	/** Načte uložený běh jako větev B (Co kdyby). */
	async openBranch(run: StoredRun) {
		if (!this.engine) return;
		const status = await this.engine.status(run.path, 0);
		const result = run.has_result ? await this.engine.result(run.path) : null;
		this.branch = { label: run.name ?? run.id, world: this.world as WorldSpec, run: { ...status, frames: [] }, frames: status.frames, result };
	}

	/** Seznam běhů projektu znovu z disku. */
	async refreshRuns() {
		if (!this.engine || !this.world || !inApp()) return;
		const listed = await this.engine.runs(this.filePath, $state.snapshot(this.world)).catch(() => null);
		if (listed) {
			this.runsDir = listed.dir;
			this.storedRuns = listed.runs;
		}
	}

	async renameRun(run: StoredRun, name: string | null) {
		await this.engine?.renameRun(run.path, name);
		await this.refreshRuns();
	}

	async deleteRun(run: StoredRun) {
		await this.engine?.deleteRun(run.path);
		if (this.run?.id === run.path) {
			this.run = null;
			this.result = null;
			this.frames = [];
			this.ranSpec = null;
		}
		if (this.branch?.run?.id === run.path) this.branch = null;
		await this.refreshRuns();
	}

	/** Slovník jazyka (linie nebo protojazyka) v roce: z běhu A, nebo z větve B. */
	async lexicon(language: string, year: number, side: 'A' | 'B' = 'A'): Promise<{ group: string; forms: Record<string, string> } | null> {
		const id = side === 'A' ? this.run?.id : this.branch?.run?.id;
		if (!id) return null;
		const fixture = this.fixtureLexicon.get(id);
		if (fixture) {
			let found: { group: string; forms: Record<string, string> } | null = null;
			for (const row of fixture) if (row.year <= year && row.languages[language]) found = row.languages[language];
			return found;
		}
		return this.engine ? this.engine.lexicon(id, language, year).catch(() => null) : null;
	}

	/** Roky se slovníkem a jazyky v nich. */
	async lexiconYears(side: 'A' | 'B' = 'A'): Promise<{ year: number; languages: string[] }[]> {
		const id = side === 'A' ? this.run?.id : this.branch?.run?.id;
		if (!id) return [];
		const fixture = this.fixtureLexicon.get(id);
		if (fixture) return fixture.map((r) => ({ year: r.year, languages: Object.keys(r.languages) }));
		return this.engine ? this.engine.lexiconYears(id).catch(() => []) : [];
	}

	/** Historie slova v jazyce: od kterého roku jaký tvar (null = jazyk pojem nemá). */
	async wordHistory(language: string, concept: string, side: 'A' | 'B' = 'A'): Promise<{ year: number; form: string | null }[]> {
		const id = side === 'A' ? this.run?.id : this.branch?.run?.id;
		if (!id) return [];
		const fixture = this.fixtureLexicon.get(id);
		if (fixture) {
			const out: { year: number; form: string | null }[] = [];
			for (const row of fixture) {
				const lex = row.languages[language];
				if (!lex) continue;
				const form = lex.forms[concept] ?? null;
				if (!out.length || out[out.length - 1].form !== form) out.push({ year: row.year, form });
			}
			return out;
		}
		return this.engine ? this.engine.wordHistory(id, language, concept).catch(() => []) : [];
	}

	/** Dialog „Otevřít“ (v aplikaci); vrátí false, když uživatel nic nevybral. */
	async openDialog(): Promise<boolean> {
		const path = await pickOpen();
		if (!path) return false;
		await this.openPath(path);
		return true;
	}

	/** Uloží projekt: v aplikaci na disk (běhy neuloženého projektu se přesunou k němu), v prohlížeči stažením. */
	async save(as = false): Promise<boolean> {
		if (!this.world) return false;
		if (!inApp()) {
			const blob = new Blob([JSON.stringify(this.world, null, 1)], { type: 'application/json' });
			const link = document.createElement('a');
			link.href = URL.createObjectURL(blob);
			link.download = this.fileName ?? 'svet.cee.json';
			link.click();
			URL.revokeObjectURL(link.href);
			this.dirty = false;
			return true;
		}
		const path = !as && this.filePath ? this.filePath : await pickSave(this.fileName ?? `${(this.world.name ?? 'svet').toLowerCase()}.cee.json`);
		if (!path) return false;
		// běhy se přesouvají při prvním uložení a při „Uložit jako“ (ne během počítání)
		const move = (!this.filePath || path !== this.filePath) && !!this.runsDir;
		if (move && (this.running || this.branch?.run?.status === 'running')) throw new Error('Běh ještě počítá; ulož projekt na nové místo, až doběhne.');
		const oldDir = this.runsDir;
		const saved = await saveProject({ path, world: $state.snapshot(this.world) as WorldSpec, runsFrom: move ? oldDir : null });
		this.filePath = path;
		this.fileName = baseName(path);
		this.dirty = false;
		this.runsDir = saved.runs.dir;
		this.storedRuns = saved.runs.runs;
		// otevřené běhy teď leží v nové složce
		if (move && oldDir) {
			const moved = (id: string | undefined) => (id && id.startsWith(oldDir) ? saved.runs.dir + id.slice(oldDir.length) : id);
			if (this.run) this.run = { ...this.run, id: moved(this.run.id)! };
			if (this.branch?.run) this.branch = { ...this.branch, run: { ...this.branch.run, id: moved(this.branch.run.id)! } };
		}
		await this.refreshRecent();
		return true;
	}

	async forgetRecent(path: string) {
		await forgetRecent(path).catch(() => undefined);
		await this.refreshRecent();
	}

	/** Vývoj: načte vzorek skutečného běhu ze static/fixtures (src-tauri: test fixture::vzorek_talvery), volitelně i větev B. */
	async loadFixture(name: string, branch?: string) {
		const data = await (await fetch(`/fixtures/${name}.json`)).json();
		this.schema = await fetch('/fixtures/schema.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
		this.load(data.world, `${name}.cee.json`);
		this.frames = data.frames;
		this.result = data.result;
		this.ranSpec = JSON.stringify(this.world);
		const end = data.world.end_year, start = data.world.start_year ?? 0;
		this.run = { id: `fixture:${name}`, status: 'done', year: end, progress: 1, start_year: start, end_year: end, seconds: data.info?.seconds ?? 0, error: null, frame_count: data.frames.length, frames: [] };
		if (data.lexicon_years) this.fixtureLexicon.set(this.run.id, data.lexicon_years);
		if (branch) {
			const b = await (await fetch(`/fixtures/${branch}.json`)).json();
			const id = `fixture:${branch}`;
			if (b.lexicon_years) this.fixtureLexicon.set(id, b.lexicon_years);
			this.branch = { label: b.info?.name ?? branch, world: b.world, run: { ...this.run, id }, frames: b.frames, result: b.result };
		}
	}

	/** Spustí větev B s upraveným zadáním (Co kdyby): z kontrolního bodu běhu A, je-li uložený. */
	async startBranch(label: string, world: WorldSpec) {
		if (!this.engine) return;
		this.branch = { label, world, run: null, frames: [], result: null };
		const parent = this.run && !this.run.id.startsWith('fixture:') ? this.run.id : null;
		const { run_id } = await this.engine.start(world, { project: this.filePath, name: label, parent });
		const poll = async () => {
			if (!this.engine || !this.branch) return;
			const status = await this.engine.status(run_id, this.branch.frames.length);
			this.branch = { ...this.branch, frames: [...this.branch.frames, ...status.frames], run: { ...status, frames: [] } };
			if (status.status === 'running') setTimeout(() => void poll(), 500);
			else {
				if (status.status === 'done') this.branch = { ...this.branch, result: await this.engine.result(run_id) };
				await this.refreshRuns();
			}
		};
		await poll();
	}

	/** Úprava zadání: uloží stav pro Zpět, provede změnu a ověří zadání. */
	edit(label: string, change: (world: WorldSpec) => void) {
		if (!this.world) return;
		this.undoStack = [...this.undoStack, { world: $state.snapshot(this.world) as WorldSpec, label }].slice(-HISTORY);
		this.redoStack = [];
		change(this.world);
		this.dirty = true;
		this.lastEdit = label;
		this.scheduleCheck();
	}

	undo() {
		const last = this.undoStack.at(-1);
		if (!last || !this.world) return;
		this.redoStack = [...this.redoStack, { world: $state.snapshot(this.world) as WorldSpec, label: last.label }];
		this.undoStack = this.undoStack.slice(0, -1);
		this.world = last.world;
		this.lastEdit = null;
		this.scheduleCheck();
	}

	redo() {
		const next = this.redoStack.at(-1);
		if (!next || !this.world) return;
		this.undoStack = [...this.undoStack, { world: $state.snapshot(this.world) as WorldSpec, label: next.label }];
		this.redoStack = this.redoStack.slice(0, -1);
		this.world = next.world;
		this.lastEdit = next.label;
		this.scheduleCheck();
	}

	private scheduleCheck() {
		if (this.checkTimer) clearTimeout(this.checkTimer);
		this.checkTimer = setTimeout(() => void this.check(), 250);
	}

	async check() {
		if (!this.engine || !this.world) return;
		this.checking = true;
		try {
			this.issues = (await this.engine.validate(this.world)).issues;
		} catch (error) {
			this.error = String(error);
		} finally {
			this.checking = false;
		}
	}

	async start() {
		if (!this.engine || !this.world) return;
		this.error = null;
		this.result = null;
		this.frames = [];
		const spec = JSON.stringify(this.world);
		try {
			const { run_id } = await this.engine.start(this.world, { project: this.filePath });
			this.ranSpec = spec;
			await this.poll(run_id);
		} catch (error) {
			if (error instanceof EngineError && error.issues.length) this.issues = error.issues;
			this.error = String(error instanceof Error ? error.message : error);
		}
	}

	private async poll(runId: string) {
		if (!this.engine) return;
		const status = await this.engine.status(runId, this.frames.length);
		this.frames = [...this.frames, ...status.frames];
		this.run = { ...status, frames: [] };
		if (status.status === 'running') {
			this.polling = setTimeout(() => void this.poll(runId), 500);
			return;
		}
		if (status.status === 'done') this.result = await this.engine.result(runId);
		// běh se zapisuje na disk sám; seznam běhů projektu se obnoví
		await this.refreshRuns();
	}

	async cancel() {
		if (this.polling) clearTimeout(this.polling);
		if (this.engine && this.run?.status === 'running') {
			await this.engine.cancel(this.run.id);
			this.run = { ...this.run, status: 'cancelled' };
		}
	}
}

export const app = new App();
