// Projekty na disku v aplikaci (Tauri): dialog Uložit/Otevřít a příkazy project_* v src-tauri.
// V prohlížeči (vývoj UI) se projekt stahuje a otevírá přes výběr souboru.
import type { StoredRun } from './engine';
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

export interface OpenedProject {
	path: string;
	world: WorldSpec;
	/** běhy projektu (složka a seznam, nejnovější první) */
	runs: { dir: string; runs: StoredRun[] };
}

export const openProject = (path: string) => invoke<OpenedProject>('project_open', { path });

/** Uloží zadání; `runsFrom` = složka běhů, která se má k projektu přesunout. */
export const saveProject = (args: { path: string; world: WorldSpec; runsFrom?: string | null }) =>
	invoke<{ path: string; runs: { dir: string; runs: StoredRun[] } }>('project_save', { path: args.path, world: args.world, runsFrom: args.runsFrom ?? null });

export interface RecentProject {
	path: string;
	name: string | null;
	/** sekundy od 1970 */
	opened: number;
	exists: boolean;
	/** počet uložených běhů */
	runs: number;
}

export const recentProjects = () => invoke<RecentProject[]>('recent_list');
export const forgetRecent = (path: string) => invoke<void>('recent_forget', { path });

/** Jméno souboru z cesty. */
export const baseName = (path: string) => path.split(/[\\/]/).pop() ?? path;
