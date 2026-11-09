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
