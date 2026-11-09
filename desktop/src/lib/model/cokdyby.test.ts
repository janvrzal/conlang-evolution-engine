import { describe, expect, it } from 'vitest';
import type { WorldSpec } from '$lib/state.svelte';
import type { StoredRun } from '$lib/engine';
import {
	branchesOf,
	branchYearOf,
	compareForms,
	differingVillages,
	focusRegions,
	folderName,
	matchLineages,
	storedBranch,
	withoutEvent,
	worldDifference,
	type Home
} from './cokdyby';

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

// ---------- malé jazyky jako variety (talvera vs. talvera-bez-politiky) ----------
import { existsSync, readFileSync } from 'node:fs';
import { frameAt, lineageFamilies } from './languages';
import { geography } from './geography';
import { differingShown, languageCount, shownHome, sideHome, sideVarieties, type Side } from './cokdyby';
import type { FrameV2 } from './export';

const fx = (name: string) => new URL(`../../../static/fixtures/${name}.json`, import.meta.url);
const have = existsSync(fx('talvera')) && existsSync(fx('talvera-bez-politiky'));

describe.skipIf(!have)('Co kdyby: variety na Talveře', () => {
	const load = (n: string) => JSON.parse(readFileSync(fx(n), 'utf8')) as Side & { frames: FrameV2[] };
	const A = have ? load('talvera') : (null as never), B = have ? load('talvera-bez-politiky') : (null as never);
	const end = (s: Side & { frames: FrameV2[] }) => frameAt(s.frames, s.result.year)!;
	const diff = (all: boolean) => {
		const ra = sideHome(end(A), A.result), rb = sideHome(end(B), B.result);
		const a = shownHome(ra, sideVarieties(A, end(A)), all), b = shownHome(rb, sideVarieties(B, end(B)), all);
		const fam = { a: lineageFamilies(A.world, A.result), b: lineageFamilies(B.world, B.result) };
		return { a, b, d: differingShown({ a: ra, b: rb }, { a, b }, fam) };
	};

	it('malé jazyky se ukážou jako variety hostitele a přepínač vrací stav enginu', () => {
		const v = sideVarieties(A, end(A));
		expect(v.host.size).toBeGreaterThan(0);
		const shown = shownHome(sideHome(end(A), A.result), v, false), raw = sideHome(end(A), A.result);
		const langs = (h: Home) => new Set([...h.values()].map((x) => x.lineage));
		expect(langs(shown).size).toBeLessThan(langs(raw).size);
		for (const [vil, h] of shown) expect(v.host.has(h.lineage)).toBe(false);
		expect(shownHome(raw, v, true)).toBe(raw);
		const c = languageCount(end(A), v, false);
		expect(c.small).toBe(v.host.size + v.orphans.length);
		expect(c.langs + c.small).toBe(Object.keys(end(A).languages).length);
		expect(languageCount(end(A), v, true)).toEqual({ langs: Object.keys(end(A).languages).length, small: 0 });
	});

	it('rozdíl Utjipengu a Luji (7 vsí, Talmurština vs. Serenština) zůstává', () => {
		const { d } = diff(false);
		const geo = geography(A.world, A.result);
		const regions = new Set([...d].map((v) => geo.name(geo.regionOf.get(v)!)));
		expect(d.size).toBe(7);
		expect(regions.has('Luji') && regions.has('Utjipeng')).toBe(true);
		expect(diff(true).d.size).toBe(7);
		// bez ochrany by se tytéž malé jazyky přiřazené v A a B různým hostitelům počítaly jako rozdíl
		const a = diff(false);
		expect(differingVillages(a.a, a.b, matchLineages(a.a, a.b, { a: lineageFamilies(A.world, A.result), b: lineageFamilies(B.world, B.result) })).size).toBeGreaterThan(7);
	});
});

describe('uložené větve a rok větvení', () => {
	const run = (o: Partial<StoredRun>) => ({ id: 'x', path: '/r/x', parent: null, branch_year: null, created: 0, ...o }) as StoredRun;
	it('folderName bere poslední díl cesty a vzorek nemá složku', () => {
		expect(folderName('/p/svet.cee.behy/20261109-162252')).toBe('20261109-162252');
		expect(folderName('/p/behy/a/')).toBe('a');
		expect(folderName('fixture:talvera')).toBeNull();
		expect(folderName(null)).toBeNull();
	});
	it('branchesOf vybere děti běhu A, nejnovější první', () => {
		const runs = [run({ id: 'a' }), run({ id: 'b', parent: 'a', created: 1 }), run({ id: 'c', parent: 'a', created: 5 }), run({ id: 'd', parent: 'z' })];
		expect(branchesOf(runs, '/p/behy/a').map((r) => r.id)).toEqual(['c', 'b']);
		expect(branchesOf(runs, 'fixture:talvera')).toEqual([]);
	});
	it('storedBranch a branchYearOf', () => {
		const r = run({ id: 'b', branch_year: 1875 });
		expect(storedBranch([r], '/p/behy/b')).toBe(r);
		expect(storedBranch([r], 'fixture:x')).toBeNull();
		expect(branchYearOf(r, 1900, 1800)).toBe(1875);
		expect(branchYearOf(null, 1875, 1800)).toBe(1875);
		expect(branchYearOf(null, undefined, 1800)).toBe(1800);
		expect(branchYearOf(null, null, null)).toBeNull();
	});
	it('compareForms porovná společné pojmy', () => {
		const c = compareForms({ water: 'a', fire: 'b', dog: 'x' }, { water: 'a', fire: 'c' }, ['water', 'fire', 'dog']);
		expect(c).toEqual({ rows: [{ concept: 'water', a: 'a', b: 'a', differs: false }, { concept: 'fire', a: 'b', b: 'c', differs: true }], changed: 1, total: 2 });
		expect(compareForms(undefined, {}, [])).toBeNull();
	});
});
