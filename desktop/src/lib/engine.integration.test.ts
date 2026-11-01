// Průchod proti běžícímu enginu: ukázkový svět → kontrola → běh → jména jazyků a nářečí.
// Spouští se jen s CEE_ENGINE_URL (např. http://127.0.0.1:8001); jinak se přeskočí.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { Engine } from './engine';
import { dialectNames, languageNames } from './naming';

const base = process.env.CEE_ENGINE_URL;

describe.skipIf(!base)('engine', () => {
	it('ukázkový svět projde kontrolou, doběhne a dá jména', { timeout: 300_000 }, async () => {
		const engine = new Engine(base!);
		const world = JSON.parse(readFileSync('static/projects/poloostrov.cee.json', 'utf8'));
		world.end_year = 400;
		world.events = world.events.filter((e: { year: number }) => e.year <= 400);
		expect((await engine.validate(world)).issues).toEqual([]);
		const { run_id } = await engine.start(world);
		let status = await engine.status(run_id, 0);
		while (status.status === 'running') {
			await new Promise((resolve) => setTimeout(resolve, 500));
			status = await engine.status(run_id, 0);
		}
		expect(status.status).toBe('done');
		expect(status.frames.at(-1)?.endonyms).toBeTruthy();
		const result = await engine.result(run_id);
		const regionName = (id: string) => world.regions.find((r: { id: string }) => r.id === id)?.name ?? id;
		const facts = result.lineages.map((l) => ({ id: l.id, parent: l.parent, endonym: l.endonym, origin: l.origin_region && regionName(l.origin_region) }));
		const cs = [...languageNames(facts, 'cs').values()];
		const en = [...languageNames(facts, 'en').values()];
		expect(cs.every((name) => name.endsWith('ština'))).toBe(true);
		expect(en.length).toBe(cs.length);
		for (const lineage of result.lineages.filter((l) => l.groups.length)) {
			const dialects = result.dialect_facts.filter((d) => d.lineage === lineage.id);
			const names = dialectNames(dialects, regionName, 'cs');
			expect(new Set(names).size).toBe(names.length);
		}
		console.log(cs, en);
	});
});
