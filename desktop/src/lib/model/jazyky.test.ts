import { describe, expect, it } from 'vitest';
import type { ExportV2, FrameV2, Lineage } from './export';
import { analogyCounts, analogyRows, centurySummary, parseFeatures, parseSym, ruleText, soundRows, endonymHistory, grammarRows, presence, riverStreams, rootRetention } from './jazyky';

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

describe('zvukové změny a analogie jazyka', () => {
	const sound = (variable: string, over: object, groups: object[]) => ({ kind: 'sound', variable, family: 'syncope', target: '{a}', operation: 'delete', features: null, segment: null, left: 'C', right: 'C', stress: 'unstressed', medial: true, year: 700, groups, ...over });
	const result = {
		change_history: [
			{ language: 'L1', groups: [], changes: [
				sound('a', { year: 800 }, [{ group: 'g1', year: 800, closed: null, relics: 0 }]),
				sound('b', { family: 'voicing', operation: 'change', features: '+voi', left: 'V', right: 'V' }, [
					{ group: 'g1', year: 700, closed: 750, relics: 2 },
					{ group: 'g2', year: 710, closed: null, relics: 3 }
				]),
				{ kind: 'analogy', variable: 'x', operation: 'level', concept: 'water', cell: 'PL', year: 900, groups: [{ group: 'g1', year: 900 }] },
				{ kind: 'analogy', variable: 'y', operation: 'level', concept: 'fire', cell: 'OBJ', year: 910, groups: [{ group: 'g1', year: 910 }, { group: 'g2', year: 911 }] },
				{ kind: 'analogy', variable: 'z', operation: 'extend', concept: null, cell: null, year: 920, groups: [] }
			] },
			{ language: 'L2', groups: [], changes: [] }
		]
	} as unknown as ExportV2;

	it('zvuky seřadí od nejrozšířenější a spočítá vsi, uzavření a relikty', () => {
		const rows = soundRows(result, 'L1');
		expect(rows.map((r) => r.key.split('#')[0])).toEqual(['b', 'a']);
		expect(rows[0]).toMatchObject({ villages: 2, closed: 1, relics: 5, year: 700 });
		expect(soundRows(result, 'L2')).toEqual([]);
		expect(soundRows(result, null)).toEqual([]);
	});

	it('zapíše pravidlo a rozebere značky', () => {
		const rows = soundRows(result, 'L1');
		expect(ruleText(rows[0])).toBe('a → [+voi] / V_V');
		expect(ruleText(rows[1])).toBe('a → ∅ / C_C');
		expect(parseSym('{i,j}')).toEqual({ kind: 'ipa', items: ['i', 'j'] });
		expect(parseSym('#')).toEqual({ kind: 'edge' });
		expect(parseFeatures('+voi,-zzz')).toEqual([
			{ plus: true, name: 'voi', known: true },
			{ plus: false, name: 'zzz', known: false }
		]);
	});

	it('analogie: řádky a souhrn podle operace', () => {
		const rows = analogyRows(result, 'L1');
		expect(rows[0]).toMatchObject({ concept: 'fire', villages: 2 });
		expect(analogyCounts(rows)).toEqual([{ operation: 'level', count: 2 }, { operation: 'extend', count: 1 }]);
	});
});
