import { describe, expect, it } from 'vitest';
import type { ExportV2, FrameV2, Lineage } from './export';
import { centurySummary, endonymHistory, grammarRows, presence, riverStreams, rootRetention } from './jazyky';

const frame = (year: number, groups: [string, number, string][], endo: Record<string, string> = {}): FrameV2 => ({
	year,
	tick: 0,
	groups: groups.map(([id, population, observed_language]) => ({ id, population, observed_language, l2_share: 0 })),
	languages: {},
	endonyms: endo,
	dialects: [],
	dialect_facts: [],
	states: [],
	census: {}
});
const lin = (id: string, start: number): Lineage => ({ id, parent: null, start_year: start, end_year: null, groups_at_start: [], groups: [], endonym: null, origin_region: null });

describe('jazyky', () => {
	const frames = [frame(0, [['a-v0', 10, 'L1'], ['b-v0', 5, 'L2']], { L1: 'aa' }), frame(100, [['a-v0', 12, 'L1'], ['b-v0', 6, 'L2']], { L1: 'ab' })];
	const lineages = [lin('L1', 0), lin('L2', 0)];
	const fam = new Map([['L1', 1], ['L2', 0]]);
	const names = new Map([['L1', 'Ábština'], ['L2', 'Bština']]);
	const pal = new Map([['L1', '#111'], ['L2', '#222']]);

	it('řadí proudy po rodinách a filtruje', () => {
		const all = riverStreams(frames, new Map(), lineages, fam, names, pal, { family: null, query: '' });
		expect(all.streams.map((s) => s.id)).toEqual(['L2', 'L1']);
		expect(all.streams[1].values).toEqual([10, 12]);
		expect(riverStreams(frames, new Map(), lineages, fam, names, pal, { family: 1, query: '' }).streams.map((s) => s.id)).toEqual(['L1']);
		expect(riverStreams(frames, new Map(), lineages, fam, names, pal, { family: null, query: 'abst' }).streams.map((s) => s.id)).toEqual(['L1']);
		expect(riverStreams(frames, new Map(), lineages, fam, names, pal, { family: 1, query: '' }, 'L2').streams.map((s) => s.id)).toEqual(['L2', 'L1']);
	});
	it('vlastní jméno jen při změně', () => {
		expect(endonymHistory(frames, 'L1')).toEqual([{ year: 0, ipa: 'aa' }, { year: 100, ipa: 'ab' }]);
	});
	it('přítomnost ve vsích', () => {
		expect(presence(frames[1], 'L1', new Map())).toEqual({ villages: 1, speakers: 12 });
	});
	it('retence kořenů je průměr skupin', () => {
		const result = { groups: [{ id: 'g1', root_retention: 0.4 }, { id: 'g2', root_retention: 0.6 }, { id: 'g3' }] } as unknown as ExportV2;
		expect(rootRetention(result, { ...lin('L', 0), groups: ['g1', 'g2', 'g3'] })).toBeCloseTo(0.5);
		expect(rootRetention(result, lin('L', 0))).toBeNull();
	});
	it('mluvnice a souhrny po stoletích', () => {
		expect(grammarRows({ PAST: { kind: 'synthetic', stage: null, exponent: 'ma', source: 'have', donor: null, order: null, reinforcer: null } }).map((r) => r.fn)).toEqual(['PAST']);
		expect(centurySummary({ '100': { analogy: 3 }, '200': {} }, ['analogy'])).toEqual([{ century: 100, counts: [3] }]);
	});
});
