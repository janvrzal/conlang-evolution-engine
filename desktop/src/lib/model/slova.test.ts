import { describe, expect, it } from 'vitest';
import type { ExportV2, LexEntry } from './export';
import { conceptList, formAreas, shortMorpheme, villageForms } from './slova';

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
});
