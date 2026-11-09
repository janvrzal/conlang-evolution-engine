// Jazyky výsledku: rodina (protojazyk), barva, jméno a jazyk doma ve vsi.
import { languagePalette, type LanguagePalette } from '$lib/ds';
import type { Locale } from '$lib/i18n.svelte';
import { languageNames } from '$lib/naming';
import type { WorldSpec } from '$lib/state.svelte';
import type { ExportV2, FrameV2, Group } from './export';
import { villageOfGroup } from './geography';

/** Linie → index rodiny (pořadí protojazyka v zadání), podle většiny skupin linie. */
export function lineageFamilies(world: WorldSpec, result: ExportV2): Map<string, number> {
	const code = new Map(result.groups.map((g) => [g.id, g.code_language]));
	const out = new Map<string, number>();
	for (const l of result.lineages) {
		const count = new Map<string, number>();
		for (const g of [...l.groups, ...l.groups_at_start]) {
			const c = code.get(g);
			if (c) count.set(c, (count.get(c) ?? 0) + 1);
		}
		const top = [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
		out.set(l.id, Math.max(0, world.languages.findIndex((x) => x.id === top)));
	}
	return out;
}

/** Barvy jazyků výsledku (odstín rodiny, světlost jazyka u velkých světů). */
export function lineagePalette(world: WorldSpec, result: ExportV2): LanguagePalette {
	const family = lineageFamilies(world, result);
	return languagePalette(result.lineages.map((l) => ({ id: l.id, start: l.start_year, end: l.end_year, parent: l.parent, family: family.get(l.id) })));
}

/** Česká/anglická jména jazyků z vlastních jmen a krajů vzniku. */
export function lineageNames(result: ExportV2, regionName: (id: string) => string, locale: Locale, frames: FrameV2[] = []): Map<string, string> {
	const last = new Map<string, string>();
	for (const f of frames) for (const [id, n] of Object.entries(f.endonyms ?? {})) if (n) last.set(id, n);
	return languageNames(
		result.lineages.map((l) => ({
			id: l.id,
			parent: l.parent,
			endonym: l.endonym ?? last.get(l.id) ?? null,
			origin: l.origin_region ? regionName(l.origin_region) : null
		})),
		locale
	);
}

type GroupLike = Pick<Group, 'id' | 'population' | 'observed_language'> & { domain?: string };

/** Ves → jazyk největší domácí skupiny. Ve snímku chybí doména; vezme se z exportu. */
export function homeLanguage(groups: GroupLike[], domainOf?: Map<string, string>): Map<string, { lineage: string; population: number; group: string }> {
	const out = new Map<string, { lineage: string; population: number; group: string }>();
	for (const g of groups) {
		const domain = g.domain ?? domainOf?.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
		if (domain !== 'home' || !g.observed_language) continue;
		const v = villageOfGroup(g.id), best = out.get(v);
		if (!best || g.population > best.population) out.set(v, { lineage: g.observed_language, population: g.population, group: g.id });
	}
	return out;
}

/** Linie → počet mluvčích doma. */
export function speakers(groups: GroupLike[], domainOf?: Map<string, string>): Map<string, number> {
	const out = new Map<string, number>();
	for (const g of groups) {
		const domain = g.domain ?? domainOf?.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
		if (domain === 'home' && g.observed_language) out.set(g.observed_language, (out.get(g.observed_language) ?? 0) + g.population);
	}
	return out;
}

/** Snímek nejbližší k roku (poslední, který rok nepřesahuje). */
export function frameAt(frames: FrameV2[], year: number): FrameV2 | null {
	let best: FrameV2 | null = null;
	for (const f of frames) if (f.year <= year && (!best || f.year > best.year)) best = f;
	return best ?? frames[0] ?? null;
}
