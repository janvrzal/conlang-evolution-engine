import { describe, expect, it } from 'vitest';
import { causeMessage, epochOf,isPersons, nameHistory, namesAsText, soundChanges, stepCause, type NameRecord, type NamesExport, type PlaceNames } from './jmena';

const record = (id: string, over: Partial<NameRecord> = {}): NameRecord => ({
	id,
	object: 'territory:m01-04',
	role: 'endonym',
	name: id,
	ipa: id,
	language: 'seren',
	lineage: 'L1',
	founded: -700,
	ended: null,
	full_name: null,
	motivation: 'compound',
	cause: null,
	tradition: 'archaic',
	meaning: 'dlouhý kámen',
	recipe: [],
	source: null,
	timeline: [],
	...over
});

describe('příčiny změn jména', () => {
	it('hlásková změna, přejetí a založení', () => {
		expect(stepCause('sound: a → e / _#')).toEqual({ kind: 'sound', detail: 'a → e / _#' });
		expect(stepCause('borrowed: seren → talmur')).toEqual({ kind: 'borrowed', detail: 'seren → talmur' });
		expect(stepCause('founded')).toEqual({ kind: 'founded', detail: '' });
		expect(stepCause('state_prestige')).toEqual({ kind: 'other', detail: 'state_prestige' });
	});
	it('klíč popisku příčiny', () => {
		expect(causeMessage('sound: a → e')).toEqual({ key: 'jmena.cause.sound', params: { detail: 'a → e' } });
		expect(causeMessage('borrowed')).toEqual({ key: 'jmena.cause.borrowed', params: {} });
		expect(causeMessage('borrowed: seren → talmur')).toEqual({ key: 'jmena.cause.borrowed_from', params: { detail: 'seren → talmur' } });
		expect(causeMessage('něco')).toEqual({ text: 'něco' });
	});
	it('počet hláskových změn', () => {
		const steps = ['founded', 'sound: a', 'sound: b', 'borrowed: x → y'].map((cause, i) => ({ year: i, ipa: '', name: '', cause }));
		expect(soundChanges(steps)).toBe(2);
	});
});

describe('epochy', () => {
	it('rok mezi pozorováními bere poslední předchozí pozorování', () => {
		const years = [-700, -600, -500];
		expect(epochOf(years, -550)).toBe(-600);
		expect(epochOf(years, -600)).toBe(-600);
		expect(epochOf(years, 1000)).toBe(-500);
		// před prvním pozorováním generátor bere první
		expect(epochOf(years, -900)).toBe(-700);
		expect(epochOf([], 0)).toBeNull();
	});
});

describe('historie jména z exportu', () => {
	const names: NamesExport = {
		records: [
			record('Avika', { ended: 1200 }),
			record('Ävegä', { founded: 1200 }),
			record('Jamen', { role: 'exonym', language: 'talmur', lineage: 'L2' }),
			record('Ymny', { role: 'exonym', language: 'idar', lineage: 'L3' })
		],
		objects: { 'territory:m01-04': { endonym: 'Ävegä', records: ['Avika', 'Ävegä', 'Jamen', 'Ymny'], exonyms: { L3: 'Ymny', L2: 'Jamen' } } }
	};
	it('současné, dřívější a cizí jméno', () => {
		const h = nameHistory(names, 'territory:m01-04')!;
		expect(h.current?.id).toBe('Ävegä');
		expect(h.earlier.map((r) => r.id)).toEqual(['Avika']);
		expect(h.exonyms.map((e) => e.lineage)).toEqual(['L2', 'L3']);
	});
	it('bez modulu jmen nebo neznámý objekt', () => {
		expect(nameHistory(null, 'territory:m01-04')).toBeNull();
		expect(nameHistory(names, 'territory:x')).toBeNull();
	});
});

describe('text ke zkopírování', () => {
	it('sídla: dnešní tvar a tvar při založení', () => {
		const result: PlaceNames = {
			region: 'm01-04',
			year: -600,
			until: 1950,
			urban: true,
			tradition: 'archaic',
			names: [
				{
					name: 'Ävegä',
					ipa: 'ævegæ',
					language: 'seren',
					lineage: 'L1',
					founded: { year: -600, name: 'Avika', ipa: 'avika', language: 'seren', lineage: 'L1', tradition: 'archaic', pattern: 'adj_noun', meaning: 'dlouhý kámen', recipe: [], words_from: -600 },
					timeline: []
				}
			]
		};
		expect(isPersons(result)).toBe(false);
		expect(namesAsText(result)).toBe('Ävegä ← Avika (dlouhý kámen)');
	});
});
