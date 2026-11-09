import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parseProject, summarize } from './projekty';
import type { WorldSpec } from '../state.svelte';

const here = dirname(fileURLToPath(import.meta.url));
const sample = (file: string) => JSON.parse(readFileSync(join(here, '..', '..', '..', 'static', 'projects', file), 'utf8')) as WorldSpec;

describe('souhrn světa', () => {
	it('Talvera: 96 krajů, 16 měst, 4 protojazyky, 59 událostí, −700–1950', () => {
		expect(summarize(sample('talvera.cee.json'))).toEqual({ name: 'Talvera', start: -700, end: 1950, regions: 96, cities: 16, languages: 4, events: 59 });
	});

	it('Poloostrov bez začátku dějin počítá od roku 0', () => {
		const s = summarize(sample('poloostrov.cee.json'));
		expect(s.start).toBe(0);
		expect(s.regions).toBe(20);
		expect(s.languages).toBe(2);
	});
});

describe('čtení souboru', () => {
	const world = sample('poloostrov.cee.json');

	it('přijme holý svět i obálku cee-project/1', () => {
		expect(parseProject(world)).toBe(world);
		expect(parseProject({ format: 'cee-project/1', world })).toBe(world);
	});

	it('cizí formát vrátí null', () => {
		expect(parseProject({ format: 'jiny/1' })).toBeNull();
		expect(parseProject({ format: 'cee-project/1', world: { format: 'jiny' } })).toBeNull();
		expect(parseProject(null)).toBeNull();
	});
});
