// Stav aplikace: otevřený svět (popis cee-v2-world/1), spojení s enginem a běh.
import { API_REVISION, Engine, EngineError, connect, type Frame, type Health, type Issue, type RunResult, type RunStatus } from './engine';

export interface WorldSpec {
	format: 'cee-v2-world/1';
	name?: string;
	seed?: number;
	start_year?: number;
	end_year: number;
	languages: { id: string; name?: string; consonants?: string[]; vowels?: string[]; grammar?: string; stress?: string; words?: Record<string, string>; endonym?: string[] }[];
	regions: { id: string; name?: string; position: [number, number]; neighbours?: string[]; villages?: number; density?: number; language?: string; terrain?: string; identity?: string }[];
	events: { kind: string; year: number; [key: string]: unknown }[];
	[key: string]: unknown;
}

type EngineState = { phase: 'connecting' } | { phase: 'offline' } | { phase: 'outdated'; health: Health } | { phase: 'ready'; health: Health };

class App {
	world = $state<WorldSpec | null>(null);
	fileName = $state<string | null>(null);
	dirty = $state(false);
	engineState = $state<EngineState>({ phase: 'connecting' });
	issues = $state<Issue[] | null>(null);
	checking = $state(false);
	run = $state<RunStatus | null>(null);
	frames = $state<Frame[]>([]);
	result = $state<RunResult | null>(null);
	error = $state<string | null>(null);
	private engine: Engine | null = null;
	private polling: ReturnType<typeof setTimeout> | null = null;

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
		if (this.world) await this.check();
	}

	load(world: WorldSpec, fileName: string | null) {
		this.world = world;
		this.fileName = fileName;
		this.dirty = false;
		this.result = null;
		this.run = null;
		this.frames = [];
		void this.check();
	}

	async loadStarter() {
		const response = await fetch('/projects/poloostrov.cee.json');
		this.load(await response.json(), 'poloostrov.cee.json');
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
		try {
			const { run_id } = await this.engine.start(this.world);
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
