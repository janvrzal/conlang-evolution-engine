import type { ExportV2, FrameV2 } from './model/export';

// Spojení s enginem. V aplikaci (Tauri) běží engine v2 přímo v procesu a volá se příkazy
// (src-tauri/src/lib.rs); v prohlížeči (vývoj UI) se hledá Python server /api/v2 na obvyklých portech.
// Tvary odpovědí jsou v obou případech stejné.

export const API_REVISION = 10;
const SIGNATURE = 'Conlang Evolution Engine';
const PORTS = Array.from({ length: 20 }, (_, i) => 8000 + i);

export interface Health {
	status: string;
	engine: string;
	version: string;
	api_revision: number;
	v2_binding_fresh?: boolean;
}

export interface Issue {
	path: string;
	/** česká zpráva enginu (výchozí text) */
	message: string;
	severity?: 'error' | 'warning';
	/** stálý kód pro překlad (dok. 36), dosazované hodnoty */
	code?: string;
	args?: Record<string, string>;
}

/** Běh uložený ve složce projektu (`cee_store::RunInfo` + `matches`, `path`). */
export interface StoredRun {
	/** jméno složky (čas spuštění) */
	id: string;
	/** cesta ke složce = id běhu pro příkazy */
	path: string;
	name: string | null;
	spec_hash: string;
	parent: string | null;
	branch_year: number | null;
	start_year: number;
	end_year: number;
	year: number;
	status: 'running' | 'done' | 'failed' | 'cancelled' | 'interrupted';
	error: string | null;
	seconds: number;
	/** sekundy od 1970 */
	created: number;
	finished: number | null;
	engine: string | null;
	frames: number;
	checkpoints: number;
	has_result: boolean;
	/** běh vznikl z tohoto zadání */
	matches: boolean;
	/** velikost složky po částech v bajtech (frames, events, lexicon, result, checkpoints) */
	size?: Record<string, number>;
}

export interface StartOptions {
	/** cesta k projektu (běh se uloží vedle něj); null = dočasná složka neuloženého projektu */
	project?: string | null;
	name?: string | null;
	/** „co kdyby“: cesta k rodičovskému běhu */
	parent?: string | null;
}

export interface RunStatus {
	id: string;
	status: 'running' | 'done' | 'failed' | 'cancelled' | 'interrupted';
	year: number;
	progress: number;
	start_year: number;
	end_year: number;
	seconds: number;
	error: string | null;
	frame_count: number;
	frames: FrameV2[];
}

/** GET /api/v2/schema: JSON schéma světa, slovní úrovně, parametry podle rolí, druhy událostí, slovníky. */
export interface EngineSchema {
	format: string;
	json_schema: Record<string, unknown>;
	/** možné hodnoty slovních úrovní (policy_levels, terrain_access, background_levels, …) */
	levels: Record<string, string[]>;
	parameters: ParameterSchema;
	/** world = slovní úrovně světa, active = pro pokročilé, fixed = skryté */
	parameters_by_role: { world: ParameterSchema; active: ParameterSchema; fixed: ParameterSchema };
	event_kinds: string[];
	vocabulary: { default: number; max: number; presets: number[]; domains: string[]; word_classes: string[]; relation_kinds: string[]; relation_directions: string[]; [key: string]: unknown };
}
export interface ParameterSchema {
	groups: { id: string; title: string }[];
	items: { name: string; kind: string; default: unknown; group?: string; title?: string; [key: string]: unknown }[];
}

export class EngineError extends Error {
	constructor(
		message: string,
		readonly issues: Issue[] = []
	) {
		super(message);
	}
}

const inTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
	const { invoke } = await import('@tauri-apps/api/core');
	return invoke<T>(command, args);
}

async function probe(base: string): Promise<Health | null> {
	try {
		const response = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(800) });
		if (!response.ok) return null;
		const health = (await response.json()) as Health;
		return health.engine === SIGNATURE ? health : null;
	} catch {
		return null;
	}
}

/** Najde engine: v aplikaci ten v procesu, v prohlížeči běžící server. */
export async function connect(): Promise<{ base: string; health: Health } | null> {
	if (inTauri()) {
		const health = await invoke<Health>('engine_health').catch(() => null);
		return health ? { base: TAURI, health } : null;
	}
	for (const base of PORTS.map((port) => `http://127.0.0.1:${port}`)) {
		const health = await probe(base);
		if (health) return { base, health };
	}
	return null;
}

/** Adresa „engine v procesu aplikace“. */
const TAURI = 'tauri:';

export class Engine {
	constructor(readonly base: string) {}

	private async request<T>(path: string, init?: RequestInit): Promise<T> {
		const response = await fetch(`${this.base}/api/v2${path}`, {
			headers: { 'content-type': 'application/json' },
			...init
		});
		const body = await response.json().catch(() => null);
		if (!response.ok) {
			const detail = body?.detail;
			throw new EngineError(typeof detail === 'string' ? detail : response.statusText, detail?.issues ?? []);
		}
		return body as T;
	}

	schema(): Promise<EngineSchema> {
		if (this.native) return this.call('engine_schema');
		return this.request('/schema');
	}

	private get native() {
		return this.base === TAURI;
	}

	/** Příkaz Tauri; odmítnutí `{ detail: { issues } }` nebo text se převede na EngineError. */
	private async call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
		try {
			return await invoke<T>(command, args);
		} catch (error) {
			const detail = (error as { detail?: { issues?: Issue[] } })?.detail;
			throw new EngineError(detail?.issues?.[0]?.message ?? String(error), detail?.issues ?? []);
		}
	}

	validate(spec: unknown): Promise<{ ok: boolean; issues: Issue[] }> {
		if (this.native) return this.call('engine_validate', { spec });
		return this.request('/validate', { method: 'POST', body: JSON.stringify(spec) });
	}

	start(spec: unknown, options: StartOptions = {}): Promise<{ run_id: string; status: string }> {
		if (this.native) return this.call('run_start', { spec, project: options.project ?? null, name: options.name ?? null, parent: options.parent ?? null });
		return this.request('/runs', { method: 'POST', body: JSON.stringify(spec) });
	}

	status(runId: string, since: number): Promise<RunStatus> {
		if (this.native) return this.call('run_status', { id: runId, since });
		return this.request(`/runs/${runId}?since=${since}`);
	}

	result(runId: string): Promise<ExportV2> {
		if (this.native) return this.call('run_result', { id: runId });
		return this.request(`/runs/${runId}/result`);
	}

	/** Běhy projektu (jen v aplikaci). */
	runs(project: string | null, spec: unknown): Promise<{ dir: string; runs: StoredRun[] }> {
		if (!this.native) return Promise.resolve({ dir: '', runs: [] });
		return this.call('runs_list', { project, spec });
	}

	/** Slovník jazyka v roce ze složky běhu (jen v aplikaci). */
	lexicon(runId: string, language: string, year: number): Promise<{ group: string; forms: Record<string, string> } | null> {
		if (!this.native) return Promise.resolve(null);
		return this.call('run_lexicon', { id: runId, language, year });
	}

	lexiconYears(runId: string): Promise<{ year: number; languages: string[] }[]> {
		if (!this.native) return Promise.resolve([]);
		return this.call('run_lexicon_years', { id: runId });
	}

	wordHistory(runId: string, language: string, concept: string): Promise<{ year: number; form: string | null }[]> {
		if (!this.native) return Promise.resolve([]);
		return this.call('run_word_history', { id: runId, language, concept });
	}

	renameRun(runId: string, name: string | null): Promise<void> {
		return this.call('run_rename', { id: runId, name });
	}

	dropCheckpoints(runId: string): Promise<void> {
		return this.call('run_drop_checkpoints', { id: runId });
	}

	deleteRun(runId: string): Promise<void> {
		return this.call('run_delete', { id: runId });
	}

	cancel(runId: string): Promise<unknown> {
		if (this.native) return this.call('run_cancel', { id: runId });
		return this.request(`/runs/${runId}`, { method: 'DELETE' });
	}
}
