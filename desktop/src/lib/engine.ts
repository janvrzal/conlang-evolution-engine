import type { ExportV2, FrameV2 } from './model/export';

// Spojení s enginem (Python, /api/v2). V Tauri engine spustí aplikace a adresu
// dá příkazem engine_url; v prohlížeči se hledá na obvyklých portech.

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

export class EngineError extends Error {
	constructor(
		message: string,
		readonly issues: Issue[] = []
	) {
		super(message);
	}
}

async function tauriUrl(): Promise<string | null> {
	if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return null;
	const { invoke } = await import('@tauri-apps/api/core');
	return invoke<string>('engine_url');
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

/** Najde běžící engine; vrátí adresu a jeho stav, nebo null. */
export async function connect(): Promise<{ base: string; health: Health } | null> {
	const fromTauri = await tauriUrl().catch(() => null);
	if (fromTauri) {
		// Aplikace engine právě spustila; Python s numpy startuje pár sekund.
		for (let attempt = 0; attempt < 40; attempt++) {
			const health = await probe(fromTauri);
			if (health) return { base: fromTauri, health };
			await new Promise((resolve) => setTimeout(resolve, 500));
		}
		return null;
	}
	for (const base of PORTS.map((port) => `http://127.0.0.1:${port}`)) {
		const health = await probe(base);
		if (health) return { base, health };
	}
	return null;
}

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

	validate(spec: unknown): Promise<{ ok: boolean; issues: Issue[] }> {
		return this.request('/validate', { method: 'POST', body: JSON.stringify(spec) });
	}

	start(spec: unknown): Promise<{ run_id: string; status: string }> {
		return this.request('/runs', { method: 'POST', body: JSON.stringify(spec) });
	}

	status(runId: string, since: number): Promise<RunStatus> {
		return this.request(`/runs/${runId}?since=${since}`);
	}

	result(runId: string): Promise<ExportV2> {
		return this.request(`/runs/${runId}/result`);
	}

	cancel(runId: string): Promise<unknown> {
		return this.request(`/runs/${runId}`, { method: 'DELETE' });
	}
}
