import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { formDistance, groupVarieties, lexicalDistanceFrom, treeDistance } from './varieties';

describe('variety malých jazyků', () => {
	it('vzdálenost tvarů a stromu', () => {
		expect(formDistance('daban', 'daban')).toBe(0);
		expect(formDistance('daban', 'dabɛn')).toBeCloseTo(0.2);
		const parent = new Map<string, string | null>([['a', null], ['b', 'a'], ['c', 'a'], ['d', 'b']]);
		expect(treeDistance('d', 'c', parent)).toBe(3);
		expect(treeDistance('b', 'a', parent)).toBe(1);
	});

	it('malý jazyk připadne nejbližšímu většímu ze stejné rodiny', () => {
		const speakers = new Map([['big1', 5000], ['big2', 3000], ['small', 300], ['other', 200]]);
		const groups = new Map([['big1', 8], ['big2', 5], ['small', 2], ['other', 1]]);
		const family = new Map([['big1', 0], ['big2', 0], ['small', 0], ['other', 1]]);
		const lin = [{ id: 'big1', parent: null }, { id: 'big2', parent: 'big1' }, { id: 'small', parent: 'big2' }, { id: 'other', parent: null }];
		const v = groupVarieties(speakers, groups, family, lin);
		expect(v.major.sort()).toEqual(['big1', 'big2']);
		expect(v.host.get('small')).toBe('big2');
		expect(v.orphans).toEqual(['other']);
	});

	const fixture = new URL('../../../static/fixtures/talvera.json', import.meta.url);
	it.skipIf(!existsSync(fixture))('Talvera 1950: méně jazyků, variety ve stejné rodině', () => {
		const { result } = JSON.parse(readFileSync(fixture, 'utf8'));
		const code = new Map<string, string>(result.groups.map((g: { id: string; code_language: string }) => [g.id, g.code_language]));
		const speakers = new Map<string, number>(), groups = new Map<string, number>(), family = new Map<string, number>();
		const fam = new Map<string, Map<string, number>>();
		for (const g of result.groups) {
			if (g.domain !== 'home' || !g.observed_language) continue;
			speakers.set(g.observed_language, (speakers.get(g.observed_language) ?? 0) + g.population);
			groups.set(g.observed_language, (groups.get(g.observed_language) ?? 0) + 1);
			const f = fam.get(g.observed_language) ?? new Map<string, number>();
			f.set(code.get(g.id)!, (f.get(code.get(g.id)!) ?? 0) + 1);
			fam.set(g.observed_language, f);
		}
		const codes = ['seren', 'talmur', 'veret', 'idar'];
		for (const [l, f] of fam) family.set(l, codes.indexOf([...f.entries()].sort((a, b) => b[1] - a[1])[0][0]));
		const v = groupVarieties(speakers, groups, family, result.lineages, lexicalDistanceFrom(result));
		expect(v.major.length).toBeLessThan(speakers.size);
		expect(v.major.length + v.host.size + v.orphans.length).toBe(speakers.size);
		for (const [s, h] of v.host) expect(family.get(s)).toBe(family.get(h));
		console.log(`Talvera 1950: ${v.major.length} jazyků + ${v.host.size + v.orphans.length} malých variet (${v.orphans.length} bez hostitele)`);
	});
});
