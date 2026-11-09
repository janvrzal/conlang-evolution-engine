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

import { addRegion, eventsUsingRegion, nextRegionId, removeRegion, toggleNeighbours } from './svet';

describe('úpravy krajů', () => {
	const world = () =>
		({
			format: 'cee-v2-world/1',
			end_year: 100,
			languages: [{ id: 'a' }],
			regions: [
				{ id: 'r1', position: [0, 0], neighbours: ['r2'], language: 'a' },
				{ id: 'r2', position: [10, 0], neighbours: ['r1'], language: 'a' },
				{ id: 'r3', position: [50, 50], neighbours: [], language: 'a', terrain: 'hills' }
			],
			events: [{ kind: 'identity', year: 10, regions: ['r3'], identity: 'strong' }]
		}) as import('$lib/state.svelte').WorldSpec;

	it('přidá kraj napojený na nejbližší', () => {
		const w = world();
		const id = addRegion(w, 48, 52, 'Nový');
		expect(id).toBe('r4');
		const r = w.regions.find((x) => x.id === id)!;
		expect(r.neighbours?.[0]).toBe('r3');
		expect(r.terrain).toBe('hills');
		expect(w.regions.find((x) => x.id === 'r3')!.neighbours).toContain('r4');
		expect(nextRegionId(w)).toBe('r5');
	});

	it('přepne sousedy oběma směry a smaže kraj s vazbami', () => {
		const w = world();
		expect(toggleNeighbours(w, 'r1', 'r2')).toBe(false);
		expect(w.regions[0].neighbours).toEqual([]);
		expect(toggleNeighbours(w, 'r1', 'r3')).toBe(true);
		expect(w.regions[2].neighbours).toEqual(['r1']);
		expect(eventsUsingRegion(w, 'r3')).toBe(1);
		removeRegion(w, 'r3');
		expect(w.regions.map((r) => r.id)).toEqual(['r1', 'r2']);
		expect(w.regions[0].neighbours).toEqual([]);
	});
});

import { parsePermeability, terrainPermeability, villagesOf, villagesProblem, villagesValue } from './svet';

describe('vsi jako rozsah a prostupnost', () => {
	it('počet vsí jako číslo nebo rozsah', () => {
		expect(villagesOf(undefined)).toEqual({ min: 4, max: 4 });
		expect(villagesOf(6)).toEqual({ min: 6, max: 6 });
		expect(villagesOf([2, 5])).toEqual({ min: 2, max: 5 });
		expect(villagesValue(3, 3)).toBe(3);
		expect(villagesValue(2, 5)).toEqual([2, 5]);
		expect(villagesProblem(2, 5)).toBeNull();
		expect(villagesProblem(5, 2)).toBe('svet.bad.villages_order');
		expect(villagesProblem(0, 2)).toBe('svet.bad.villages');
		expect(villagesProblem(1, 13)).toBe('svet.bad.villages');
		expect(villagesProblem(1.5, 3)).toBe('svet.bad.villages');
	});

	it('prostupnost z terénu a z pole', () => {
		const schema = { parameters: { items: [{ name: 'terrain_access', default: { plain: 1, hills: 0.6, mountains: 0.3, island: 0.2 } }] } };
		expect(terrainPermeability('hills', schema)).toBe(0.6);
		expect(terrainPermeability(undefined, schema)).toBe(1);
		expect(terrainPermeability('hills', schema, { terrain_access: { hills: 0.5 } })).toBe(0.5);
		expect(terrainPermeability('hills', null)).toBeNull();
		expect(parsePermeability('0,4')).toBe(0.4);
		expect(parsePermeability('1.2')).toBeNull();
		expect(parsePermeability('')).toBeNull();
	});
});
