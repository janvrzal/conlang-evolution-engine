// Výpočty obrazovky Projekty: souhrn světa pro karty, ukázkové světy a čtení souboru .cee.
import type { WorldSpec } from '../state.svelte';

/** Ukázkové světy ze static/projects (načítají se fetch a otevírají přes app.load). */
export const SAMPLES = [
	{ id: 'talvera', file: 'talvera.cee.json' },
	{ id: 'poloostrov', file: 'poloostrov.cee.json' }
] as const;

export interface WorldSummary {
	name: string | null;
	start: number;
	end: number;
	regions: number;
	/** kraje s aspoň jedním městem */
	cities: number;
	languages: number;
	events: number;
}

export function summarize(world: WorldSpec): WorldSummary {
	return {
		name: world.name ?? null,
		start: world.start_year ?? 0,
		end: world.end_year,
		regions: world.regions.length,
		cities: world.regions.filter((r) => (r.city ?? 0) > 0).length,
		languages: world.languages.length,
		events: world.events.length
	};
}

/** Svět z čteného souboru: holý popis `cee-v2-world/1`, nebo obálka `cee-project/1`. Jinak null. */
export function parseProject(data: unknown): WorldSpec | null {
	const obj = data as { format?: unknown; world?: unknown } | null;
	const world = obj?.format === 'cee-project/1' ? obj.world : data;
	const spec = world as WorldSpec | null;
	return spec && typeof spec === 'object' && spec.format === 'cee-v2-world/1' ? spec : null;
}

// ---- Běhy projektu ----
import type { StoredRun } from '../engine';

export type RunStatusKey = 'done' | 'running' | 'failed' | 'cancelled' | 'interrupted';

/** Klíč popisku stavu běhu (`projekty.status_<klíč>`); neznámý stav se bere jako přerušený. */
export function runStatusKey(run: Pick<StoredRun, 'status'>): RunStatusKey {
	const known: RunStatusKey[] = ['done', 'running', 'failed', 'cancelled', 'interrupted'];
	return known.includes(run.status) ? run.status : 'interrupted';
}

/** Nejnovější běh první; při shodě času podle jména složky. */
export function sortRuns(runs: readonly StoredRun[]): StoredRun[] {
	return [...runs].sort((a, b) => b.created - a.created || b.id.localeCompare(a.id));
}

/** Čas spuštění (sekundy od 1970) zkráceně podle jazyka rozhraní. */
export function formatRunTime(seconds: number, locale: string): string {
	return new Date(seconds * 1000).toLocaleString(locale, { day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Doba výpočtu: „45 s“, „3 min 20 s“, „1 h 05 min“. */
export function formatDuration(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 60) return `${s} s`;
	const m = Math.floor(s / 60);
	if (m < 60) return `${m} min ${String(s % 60).padStart(2, '0')} s`.replace(' 00 s', '');
	return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

/** Zobrazované jméno: vlastní jméno, jinak čas spuštění. */
export function runTitle(run: Pick<StoredRun, 'name' | 'created'>, locale: string): string {
	const name = run.name?.trim();
	return name ? name : formatRunTime(run.created, locale);
}

/** Jméno rodiče větve (jméno nebo čas), nebo samotné id, když rodič v seznamu není. */
export function parentTitle(run: Pick<StoredRun, 'parent'>, runs: readonly StoredRun[], locale: string): string | null {
	if (!run.parent) return null;
	const p = runs.find((r) => r.id === run.parent || r.path === run.parent);
	return p ? runTitle(p, locale) : run.parent;
}

/** Prázdné jméno při přejmenování = zrušit vlastní jméno. */
export const normalizeRunName = (value: string): string | null => value.trim() || null;
