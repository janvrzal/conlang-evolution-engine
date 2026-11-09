// Projekty na disku v aplikaci (Tauri): dialog Uložit/Otevřít a příkazy project_* v src-tauri.
// V prohlížeči (vývoj UI) se projekt stahuje a otevírá přes výběr souboru.
import type { ExportV2, FrameV2 } from './model/export';
import type { WorldSpec } from './state.svelte';

export const inApp = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
	const { invoke } = await import('@tauri-apps/api/core');
	return invoke<T>(command, args);
}

const FILTERS = [{ name: 'Svět CEE', extensions: ['json'] }];

/** Dialog „Otevřít“; null = zrušeno. */
export async function pickOpen(): Promise<string | null> {
	const { open } = await import('@tauri-apps/plugin-dialog');
	const path = await open({ multiple: false, directory: false, filters: FILTERS });
	return typeof path === 'string' ? path : null;
}

/** Dialog „Uložit jako“; null = zrušeno. */
export async function pickSave(defaultName: string): Promise<string | null> {
	const { save } = await import('@tauri-apps/plugin-dialog');
	const path = await save({ defaultPath: defaultName, filters: FILTERS });
	return path ?? null;
}

export interface SavedRun {
	format: 'cee-run/1';
	spec: WorldSpec;
	seconds: number;
	frames: FrameV2[];
	result: ExportV2;
}

export interface OpenedProject {
	path: string;
	world: WorldSpec;
	run: SavedRun | null;
	/** uložený výsledek vznikl z tohoto zadání */
	run_matches: boolean;
}

export const openProject = (path: string) => invoke<OpenedProject>('project_open', { path });

export const saveProject = (args: { path: string; world: WorldSpec; runId?: string | null; spec?: WorldSpec | null; resultFrom?: string | null }) =>
	invoke<{ path: string; result: string | null }>('project_save', {
		path: args.path,
		world: args.world,
		runId: args.runId ?? null,
		spec: args.spec ?? null,
		resultFrom: args.resultFrom ?? null
	});

export const saveResult = (path: string, runId: string, spec: WorldSpec) => invoke<{ result: string }>('result_save', { path, runId, spec });

export interface RecentProject {
	path: string;
	name: string | null;
	/** sekundy od 1970 */
	opened: number;
	exists: boolean;
	has_result: boolean;
}

export const recentProjects = () => invoke<RecentProject[]>('recent_list');
export const forgetRecent = (path: string) => invoke<void>('recent_forget', { path });

/** Jméno souboru z cesty. */
export const baseName = (path: string) => path.split(/[\\/]/).pop() ?? path;
