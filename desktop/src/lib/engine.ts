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
	message: string;
	severity?: 'error' | 'warning';
}

export interface RunStatus {
	id: string;
	status: 'running' | 'done' | 'failed' | 'cancelled';
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

	start(spec: unknown): Promise<{ run_id: string; status: string }> {
		if (this.native) return this.call('run_start', { spec });
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

	cancel(runId: string): Promise<unknown> {
		if (this.native) return this.call('run_cancel', { id: runId });
		return this.request(`/runs/${runId}`, { method: 'DELETE' });
	}
}
