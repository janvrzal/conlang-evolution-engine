import { describe, expect, it } from 'vitest';
import type { WorldSpec } from '$lib/state.svelte';
import { cityOptions, levelsInOrder, regionsPerLanguage, worldWarnings } from './svet';

const world = (regions: WorldSpec['regions']): WorldSpec => ({ format: 'cee-v2-world/1', end_year: 100, languages: [], regions, events: [] });

describe('upozornění ke světu', () => {
	it('kraje bez města a kraje s jediným jazykem', () => {
		const w = world([
			{ id: 'a', position: [0, 0], language: 'x', neighbours: ['b'], city: 0 },
			{ id: 'b', position: [1, 0], language: 'x', neighbours: ['a', 'c'], city: 3 },
			{ id: 'c', position: [2, 0], language: 'y', neighbours: ['b'] }
		]);
		const [noCity, single] = worldWarnings(w);
		expect(noCity).toEqual({ kind: 'no_city', regions: ['a', 'c'] });
		expect(single).toEqual({ kind: 'single_language', regions: ['a'] });
	});
	it('svět bez upozornění', () => {
		expect(worldWarnings(world([{ id: 'a', position: [0, 0], language: 'x', neighbours: [], city: 2 }]))).toEqual([]);
	});
	it('počty krajů podle jazyka', () => {
		const m = regionsPerLanguage(world([{ id: 'a', position: [0, 0], language: 'x' }, { id: 'b', position: [0, 0], language: 'x' }]));
		expect(m.get('x')).toBe(2);
	});
});

describe('nabídky', () => {
	it('velikost města zachová neobvyklou hodnotu', () => {
		expect(cityOptions(2.5)).toEqual([0, 2, 2.5, 3, 4, 6]);
		expect(cityOptions(null)).toEqual([0, 2, 3, 4, 6]);
	});
	it('úrovně podle pořadí', () => {
		expect(levelsInOrder(['calm', 'none', 'normal', 'turbulent'], ['none', 'calm', 'normal', 'turbulent'])).toEqual(['none', 'calm', 'normal', 'turbulent']);
	});
});
