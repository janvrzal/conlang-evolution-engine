import { describe, expect, it } from 'vitest';
import type { WorldSpec } from '$lib/state.svelte';
import { differingVillages, focusRegions, matchLineages, withoutEvent, worldDifference, type Home } from './cokdyby';

const h = (entries: [string, string][]): Home => new Map(entries.map(([v, lineage]) => [v, { lineage, population: 1, group: v }]));
const world = (events: { kind: string; year: number }[]) => ({ format: 'cee-v2-world/1', end_year: 100, languages: [], regions: [], events }) as unknown as WorldSpec;

describe('Co kdyby', () => {
	it('spáruje jazyk B s A podle společných vsí', () => {
		const a = h([['v1', 'A1'], ['v2', 'A1'], ['v3', 'A2']]);
		const b = h([['v1', 'B1'], ['v2', 'B1'], ['v3', 'B9']]);
		const m = matchLineages(a, b);
		expect(m.get('B1')).toBe('A1');
		expect(m.get('B9')).toBe('A2');
	});
	it('ves s jiným jazykem je rozdílná, nespárovaný jazyk B je vždy jiný', () => {
		const a = h([['v1', 'A1'], ['v2', 'A1']]);
		const b = h([['v1', 'B1'], ['v2', 'B2']]);
		const m = new Map<string, string | null>([['B1', 'A1'], ['B2', null]]);
		expect([...differingVillages(a, b, m)]).toEqual(['v2']);
	});
	it('rámování přidá sousedy rozdílných krajů', () => {
		const f = focusRegions(new Set(['v1']), new Map([['v1', 'r1']]), (r) => (r === 'r1' ? ['r2'] : []));
		expect([...f.core]).toEqual(['r1']);
		expect([...f.all].sort()).toEqual(['r1', 'r2']);
	});
	it('najde rozdílné události a rok větvení', () => {
		const d = worldDifference(world([{ kind: 'x', year: 10 }, { kind: 'y', year: 50 }]), world([{ kind: 'x', year: 10 }]));
		expect(d.onlyA).toEqual([{ kind: 'y', year: 50 }]);
		expect(d.year).toBe(50);
	});
	it('vynechání události nemění původní zadání', () => {
		const w = world([{ kind: 'x', year: 1 }, { kind: 'y', year: 2 }]);
		expect(withoutEvent(w, 0).events).toEqual([{ kind: 'y', year: 2 }]);
		expect(w.events).toHaveLength(2);
	});
});
