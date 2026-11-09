import { describe, expect, it } from 'vitest';
import type { ExportV2, LexEntry } from './export';
import { conceptList, formAreas, historyLayers, lineageChain, shortMorpheme, villageForms, villageFormsAt } from './slova';

const e = (form: string, language = 'seren', loan = false): LexEntry => ({ form, origin: 'inherited', language, loan, root: null, base: null, since: null, sources: [] });
const result = {
	groups: [
		{ id: 'a', code_language: 'seren' },
		{ id: 'b', code_language: 'seren' }
	],
	lexicon: { a: { water: e('daban'), fire: e('x') }, b: { water: e('aru', 'idar') } }
} as unknown as ExportV2;

describe('slova', () => {
	it('sestaví seznam pojmů', () => {
		expect(conceptList(result, 'en').map((c) => c.value)).toEqual(['fire', 'water']);
	});
	it('tvary ve vsích a cizí původ', () => {
		const home = new Map([['v1', { lineage: 'L', group: 'a' }], ['v2', { lineage: 'M', group: 'b' }], ['v3', { lineage: 'L', group: 'a' }]]);
		const forms = villageForms(result, home, 'water');
		expect(forms.get('v2')?.foreign).toBe(true);
		expect(forms.get('v1')?.foreign).toBe(false);
		expect(formAreas(forms)).toEqual([
			{ form: 'daban', villages: 2, foreign: false },
			{ form: 'aru', villages: 1, foreign: true }
		]);
	});
	it('zkrátí značku morfému', () => {
		expect(shortMorpheme('morpheme:e9471cb4a0')).toBe('e9471c');
		expect(shortMorpheme(null)).toBeNull();
	});
	it('tvary ve vsích podle slovníku jazyka v roce', () => {
		const home = new Map([['v1', { lineage: 'L', group: 'a' }], ['v2', { lineage: 'M', group: 'b' }], ['v3', { lineage: 'N', group: 'c' }]]);
		const lex: Record<string, Record<string, string>> = { L: { water: 'daba' }, M: { water: 'daba' } };
		const forms = villageFormsAt(home, 'water', (l) => lex[l]);
		expect([...forms.keys()]).toEqual(['v1', 'v2']);
		expect(formAreas(forms)).toEqual([{ form: 'daba', villages: 2, foreign: false }]);
	});
	it('řetěz linií po rodičích', () => {
		const lin = [{ id: 'c', parent: 'b' }, { id: 'b', parent: 'a' }, { id: 'a', parent: null }];
		expect(lineageChain(lin, 'c')).toEqual(['c', 'b', 'a']);
		expect(lineageChain(lin, 'x')).toEqual([]);
	});
	it('vrstvy od nejnovější, změna jazyka červeně, protoforma na konci', () => {
		const chain = [
			{ id: 'c', history: [{ year: 1950, form: 'hn' }] },
			{ id: 'b', history: [{ year: -600, form: 'dab' }, { year: 1700, form: 'dw' }, { year: 1900, form: 'gar' }, { year: 1950, form: 'gar' }] }
		];
		const layers = historyLayers(chain, { language: 'seren', form: 'daban', year: -700 }, 1950);
		expect(layers.map((l) => [l.form, l.changed])).toEqual([['hn', true], ['gar', false], ['dw', false], ['dab', true], ['daban', false]]);
		expect(layers[4].proto).toBe(true);
		expect(historyLayers(chain, null, 1800).map((l) => l.form)).toEqual(['dw', 'dab']);
	});
});
