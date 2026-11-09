import { describe, expect, it } from 'vitest';
import type { MessageKey } from '$lib/i18n.svelte';
import {
	centuries,
	classOf,
	filterEvents,
	kindKey,
	listEvents,
	mergeRows,
	regionId,
	type KronikaContext,
	type RawEvent
} from './kronika';

// Falešný překlad: vrátí klíč a parametry, aby šlo čekat konkrétní větu.
const tr = (key: MessageKey, params?: Record<string, string | number>) => (params ? `${key}|${Object.values(params).join(',')}` : String(key));
const ctx: KronikaContext = {
	tr,
	names: {
		region: (id) => `R(${id})`,
		lineage: (id) => `L(${id})`,
		language: (code) => `J(${code})`,
		state: (id) => `S(${id})`,
		known: (id) => /^m\d\d-\d\d$/.test(id)
	}
};

describe('kronika: id kraje', () => {
	it('z vsi, skupiny a sloučené skupiny vezme kraj', () => {
		const known = ctx.names.known;
		expect(regionId('m07-02-v0>seren', known)).toBe('m07-02');
		expect(regionId('m03-06+m06-03-v0', known)).toBe('m03-06');
		expect(regionId('m02-03-0', known)).toBe('m02-03');
		expect(regionId('m01-04', known)).toBe('m01-04');
	});
});

describe('kronika: druhy a třídy', () => {
	it('názvy z kind.* a z kronika.kind.*, neznámé zůstanou', () => {
		expect(kindKey('state')).toBe('kind.state');
		expect(kindKey('settlement')).toBe('kronika.kind.settlement');
		expect(kindKey('unknown_kind')).toBeNull();
	});

	it('třída: dějiny autora, jazyky (vznik a zánik), zbytek společnost', () => {
		expect(classOf('author', 'state')).toBe('author');
		expect(classOf('history', 'language_split')).toBe('lang');
		expect(classOf('history', 'codification')).toBe('soc');
	});
});

const world: RawEvent[] = [
	{ kind: 'settlement', year: 1850, from: 'm01-01', to: 'm02-02', share: 0.12, settlements: 1 },
	{ kind: 'settlement', year: 1850, from: 'm01-03', to: 'm02-02', share: 0.2, settlements: 2 },
	{ kind: 'state', year: 1875, id: 'istren', name: 'Istren', capital: 'm02-02', regions: ['m02-02'], policy: 'enforced', border: 'closed' }
];
const history: RawEvent[] = [
	{ kind: 'language_split', year: 1850.0, lineage: 'lineage:a', parent: 'lineage:b' },
	{ kind: 'stress_rule_changed', year: 1850.0, group: 'm01-01-v0', old: 'penult', new: 'initial' },
	{ kind: 'grammaticalized', year: 1900, group: 'm01-01-v0>seren', function: 'FUTURE' },
	{ kind: 'codification', year: 1850.0, source: 'm01-04-v0' }
];

describe('kronika: události a řádky', () => {
	const events = listEvents(world, history, ctx);

	it('drobné změny (přízvuk, mluvnice) nejsou řádky a výsledek je seřazený od nejstarší', () => {
		expect(events.some((e) => e.kind === 'stress_rule_changed' || e.kind === 'grammaticalized')).toBe(false);
		expect(events.map((e) => e.year)).toEqual([1850, 1850, 1850, 1850, 1875]);
		expect(events[0].source).toBe('author');
	});

	it('popisek jazyka a kraje jde přes jména z kontextu', () => {
		const split = events.find((e) => e.kind === 'language_split')!;
		expect(split.title).toBe('kronika.ev.language_split.title|L(lineage:a),L(lineage:b)');
		expect(split.cls).toBe('lang');
	});

	it('stejné události jednoho roku a druhu se sloučí s počtem, i napříč zdroji', () => {
		const rows = mergeRows(events);
		const settlements = rows.find((r) => r.kind === 'settlement')!;
		expect(settlements.count).toBe(2);
		expect(settlements.title).toBe('kronika.kind.settlement');
		expect(settlements.members.map((m) => m.key)).toEqual(['a0', 'a1']);
		expect(rows.find((r) => r.kind === 'codification')!.count).toBe(1);
		const withEcho = mergeRows(listEvents(world, [{ kind: 'state', year: 1875, id: 'istren', name: 'Istren', policy: 'enforced', border: 'closed', regions: [] }], ctx));
		expect(withEcho.find((r) => r.kind === 'state')).toMatchObject({ count: 2, source: 'author', cls: 'author' });
	});

	it('vzniklý stát bez hranice napíše jen politiku', () => {
		const state = listEvents([{ kind: 'state', year: -475, id: 'varad', name: 'Varadská říše', policy: 'tolerant' }], [], ctx)[0];
		expect(state.text).toBe('kronika.ev.state.policy|kronika.policy.tolerant');
	});

	it('filtr podle třídy a hledání', () => {
		const onlyAuthor = filterEvents(events, { show: { author: true, soc: false, lang: false }, query: '' });
		expect(onlyAuthor.every((e) => e.source === 'author')).toBe(true);
		const found = filterEvents(events, { show: { author: true, soc: true, lang: true }, query: 'istren' });
		expect(found.map((e) => e.kind)).toEqual(['state']);
	});
});

describe('kronika: století a souhrn', () => {
	const summary = {
		'1800': { phonologized: 20, established: 7, analogy: 3, stress_rule_changed: 2, stress_strength_changed: 1, innovation: 0 },
		'1900': { grammaticalized: 4, exapted: 1, extinct: 5 }
	};

	it('souhrn sčítá zvuk (established + phonologized) a přízvuk, nuly vynechá', () => {
		const rows = mergeRows(listEvents(world, history, ctx));
		const blocks = centuries(-700, 1950, summary, rows);
		const c1800 = blocks.find((c) => c.key === 1800)!;
		expect(c1800.summary).toEqual([
			{ id: 'sound', value: 27 },
			{ id: 'stress', value: 3 },
			{ id: 'analogy', value: 3 }
		]);
		expect(c1800.rows.length).toBe(4);
		expect(blocks.find((c) => c.key === 1900)!.summary.map((s) => s.id)).toEqual(['grammar', 'extinct']);
	});

	it('rozsah od začátku do konce běhu, poslední století končí koncem běhu', () => {
		const blocks = centuries(-700, 1950, undefined, []);
		expect(blocks[0]).toMatchObject({ key: -700, from: -700, to: -601 });
		expect(blocks.at(-1)).toMatchObject({ key: 1900, from: 1900, to: 1950 });
		expect(blocks.length).toBe(27);
	});
});
