import { describe, expect, it } from 'vitest';
import { dialectNames, languageNames, regionAdjective, romanize } from './naming';

describe('jména', () => {
	it('přepíše IPA do latinky', () => {
		expect(romanize('kʷita')).toBe('Kwita');
		expect(romanize('t͡ʃimaka')).toBe('Čimaka');
	});

	it('tvoří přídavná jména krajů', () => {
		expect(regionAdjective('Su')).toBe('suská');
		expect(regionAdjective('Totsa')).toBe('totská');
		expect(regionAdjective('Lisk', 'n')).toBe('liscké');
	});

	it('pojmenuje dceřiný jazyk podle kraje, dokud má stejné vlastní jméno', () => {
		const languages = [
			{ id: 'a', parent: null, endonym: 'teda', origin: null },
			{ id: 'b', parent: 'a', endonym: 'teda', origin: 'Su' },
			{ id: 'c', parent: 'a', endonym: 'ɡəlus', origin: 'Teth' }
		];
		expect([...languageNames(languages, 'cs').values()]).toEqual(['tedština', 'suská tedština', 'gelusština']);
		expect([...languageNames(languages, 'en').values()]).toEqual(['Teda', 'Su Teda', 'Gelus']);
	});

	it('pojmenuje nářečí od obecného k přesnému', () => {
		const dialects = [
			{ regions: ['su'], direction: 'east', terrain: 'plain', sole: false, local: 'east' },
			{ regions: ['su'], direction: 'east', terrain: 'plain', sole: false, local: 'west' },
			{ regions: ['ulm'], direction: 'south', terrain: 'mountains', sole: false }
		];
		const name = (id: string) => ({ su: 'Su', ulm: 'Ulm' })[id] ?? id;
		expect(dialectNames(dialects, name, 'cs')).toEqual(['východní suské nářečí', 'západní suské nářečí', 'horské nářečí']);
		expect(dialectNames(dialects, name, 'en')).toEqual(['Eastern Su dialect', 'Western Su dialect', 'Highland dialect']);
	});
});
