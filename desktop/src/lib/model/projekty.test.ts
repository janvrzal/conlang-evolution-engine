import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parseProject, summarize } from './projekty';
import type { WorldSpec } from '../state.svelte';

const here = dirname(fileURLToPath(import.meta.url));
const sample = (file: string) => JSON.parse(readFileSync(join(here, '..', '..', '..', 'static', 'projects', file), 'utf8')) as WorldSpec;

describe('souhrn světa', () => {
	it('Talvera (svět Imini): 96 krajů, 16 měst, 4 protojazyky, 59 událostí, −700–1950', () => {
		expect(summarize(sample('talvera.cee.json'))).toEqual({ name: 'Imini', start: -700, end: 1950, regions: 96, cities: 16, languages: 4, events: 59 });
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

import { formatDuration, normalizeRunName, parentTitle, runStatusKey, runTitle, sortRuns } from './projekty';
import type { StoredRun } from '../engine';

const run = (o: Partial<StoredRun>): StoredRun =>
	({ id: 'a', path: '/p/a', name: null, parent: null, branch_year: null, status: 'done', created: 100, ...o }) as StoredRun;

describe('běhy projektu', () => {
	it('řadí nejnovější první', () => {
		expect(sortRuns([run({ id: 'a', created: 1 }), run({ id: 'b', created: 3 }), run({ id: 'c', created: 2 })]).map((r) => r.id)).toEqual(['b', 'c', 'a']);
	});
	it('stav: neznámý je přerušený', () => {
		expect(runStatusKey(run({ status: 'failed' }))).toBe('failed');
		expect(runStatusKey(run({ status: 'x' as never }))).toBe('interrupted');
	});
	it('doba', () => {
		expect(formatDuration(45)).toBe('45 s');
		expect(formatDuration(200)).toBe('3 min 20 s');
		expect(formatDuration(180)).toBe('3 min');
		expect(formatDuration(3900)).toBe('1 h 05 min');
	});
	it('jméno, jinak čas; rodič', () => {
		expect(runTitle(run({ name: ' Moje ' }), 'cs')).toBe('Moje');
		expect(runTitle(run({ name: null, created: 0 }), 'cs')).toMatch(/1970/);
		const parent = run({ id: 'p', path: '/p/p', name: 'Základ' });
		expect(parentTitle(run({ parent: 'p' }), [parent], 'cs')).toBe('Základ');
		expect(parentTitle(run({ parent: 'zmizel' }), [parent], 'cs')).toBe('zmizel');
		expect(parentTitle(run({}), [parent], 'cs')).toBeNull();
	});
	it('prázdné jméno ruší jméno', () => {
		expect(normalizeRunName('  ')).toBeNull();
		expect(normalizeRunName(' A ')).toBe('A');
	});
});
