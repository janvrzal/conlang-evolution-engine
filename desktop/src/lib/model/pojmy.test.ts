import { describe, expect, it } from 'vitest';
import {
	BASE_CONCEPTS,
	BASE_SIZE,
	checkDraft,
	conceptOf,
	customConcepts,
	draftOf,
	emptyDraft,
	filterConcepts,
	isInvented,
	sizeFactor,
	sizeOf,
	sizeOptions
} from './pojmy';

describe('základní pojmy', () => {
	it('jsou 149 unikátních id s doménou z enginu', () => {
		expect(BASE_CONCEPTS.length).toBe(BASE_SIZE);
		expect(new Set(BASE_CONCEPTS.map((c) => c.id)).size).toBe(149);
		expect(BASE_CONCEPTS.find((c) => c.id === 'water')?.domain).toBe('core');
	});
});

describe('velikost slovníku', () => {
	it('volby jsou předvolby a maximum bez duplicit, vzestupně', () => {
		expect(sizeOptions({ presets: [149, 200, 500, 1000], max: 1453 })).toEqual([149, 200, 500, 1000, 1453]);
		expect(sizeOptions({ presets: [149, 1453], max: 1453 })).toEqual([149, 1453]);
	});

	it('násobek běhu: pod dvě jednotky s desetinou, výš celé číslo', () => {
		expect(sizeFactor(149)).toBe(1);
		expect(sizeFactor(200)).toBe(1.3);
		expect(sizeFactor(500)).toBe(3);
		expect(sizeFactor(1000)).toBe(7);
		expect(sizeFactor(1453)).toBe(10);
	});

	it('bez zápisu platí základní velikost', () => {
		expect(sizeOf(null)).toBe(BASE_SIZE);
		expect(sizeOf({ format: 'cee-v2-world/1', end_year: 1 } as never)).toBe(BASE_SIZE);
		expect(sizeOf({ format: 'cee-v2-world/1', end_year: 1, vocabulary: 500 } as never)).toBe(500);
	});
});

describe('vlastní pojmy', () => {
	it('bez vazby na WOLD ani Concepticon je vymyšlený', () => {
		expect(isInvented({})).toBe(true);
		expect(isInvented({ wold: '2-91' })).toBe(false);
		expect(isInvented({ concepticon: 1209 })).toBe(false);
	});

	it('prázdná pole se do zadání nepíšou a číslo Concepticonu je číslo', () => {
		const d = { ...emptyDraft(), id: ' hraz ', gloss: 'dyke', concepticon: '1209' };
		expect(conceptOf(d)).toEqual({ id: 'hraz', gloss: 'dyke', concepticon: 1209 });
	});

	it('vztah k příbuznému pojmu se zapíše jako related s druhem', () => {
		const d = { ...emptyDraft(), id: 'hraz', related: 'water', relation_kind: 'derivation' };
		expect(conceptOf(d).related).toEqual([{ concept: 'water', kind: 'derivation', direction: null, weight: null }]);
	});

	it('draftOf a conceptOf jdou zpět beze ztráty polí', () => {
		const c = { id: 'hraz', gloss: 'dyke', domain: 'culture' as const, word_class: 'noun' as const, wold: '2-91', related: [{ concept: 'water', kind: 'derivation' as const }] };
		expect(conceptOf(draftOf(c))).toEqual({ id: 'hraz', gloss: 'dyke', domain: 'culture', word_class: 'noun', wold: '2-91', related: [{ concept: 'water', kind: 'derivation', direction: null, weight: null }] });
	});

	it('ověření id: prázdné, špatný tvar, obsazené (základní i vlastní)', () => {
		const taken = new Set(['water']);
		expect(checkDraft({ ...emptyDraft() }, taken).id).toBe('empty');
		expect(checkDraft({ ...emptyDraft(), id: 'a b' }, taken).id).toBe('bad');
		expect(checkDraft({ ...emptyDraft(), id: 'water' }, taken).id).toBe('taken');
		expect(checkDraft({ ...emptyDraft(), id: 'hraz.1' }, taken).id).toBeNull();
		expect(checkDraft({ ...emptyDraft(), id: 'hráz' }, taken).id).toBeNull();
	});

	it('ověření Concepticonu: prázdné nebo celé číslo od 1', () => {
		const taken = new Set<string>();
		expect(checkDraft({ ...emptyDraft(), id: 'x', concepticon: '' }, taken).concepticon).toBe(false);
		expect(checkDraft({ ...emptyDraft(), id: 'x', concepticon: '12' }, taken).concepticon).toBe(false);
		expect(checkDraft({ ...emptyDraft(), id: 'x', concepticon: '0' }, taken).concepticon).toBe(true);
		expect(checkDraft({ ...emptyDraft(), id: 'x', concepticon: '1.5' }, taken).concepticon).toBe(true);
	});

	it('světy bez pole concepts vrátí prázdný seznam', () => {
		expect(customConcepts(null)).toEqual([]);
	});
});

describe('hledání pojmů', () => {
	const list = [
		{ id: 'water', label: 'voda' },
		{ id: 'stone', label: 'kámen' }
	];
	it('hledá v id i v popisku bez velikosti písmen', () => {
		expect(filterConcepts(list, 'WAT', (c) => c.label)).toEqual([list[0]]);
		expect(filterConcepts(list, 'kám', (c) => c.label)).toEqual([list[1]]);
		expect(filterConcepts(list, '  ', (c) => c.label)).toHaveLength(2);
	});
});
