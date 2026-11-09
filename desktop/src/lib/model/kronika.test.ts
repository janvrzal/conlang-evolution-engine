import { describe, expect, it } from 'vitest';
import type { MessageKey } from '$lib/i18n.svelte';
import {
	centuries,
	classOf,
	filterEvents,
	kindCounts,
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
	it('názvy ze sdíleného kind.* a jen z kronika.kind.* (přízvuk, souhrnové druhy), neznámé zůstanou', () => {
		expect(kindKey('state')).toBe('kind.state');
		expect(kindKey('settlement')).toBe('kind.settlement');
		expect(kindKey('language_ended')).toBe('kind.language_ended');
		expect(kindKey('stress_rule_changed')).toBe('kronika.kind.stress_rule_changed');
		expect(kindKey('milestone')).toBe('kronika.kind.milestone');
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
		expect(settlements.title).toBe('kind.settlement');
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
		const onlyAuthor = filterEvents(events, { show: { author: true, soc: false, lang: false, case: true }, query: '' });
		expect(onlyAuthor.every((e) => e.source === 'author')).toBe(true);
		const found = filterEvents(events, { show: { author: true, soc: true, lang: true, case: true }, query: 'istren' });
		expect(found.map((e) => e.kind)).toEqual(['state']);
	});
});

describe('kronika: studijní případy', () => {
	const worldCases: RawEvent[] = [
		{ kind: 'annexation', year: 1875, state: 'istren', regions: ['m02-02'], study_case: 'Tvrdá politika Istrenu' },
		{ kind: 'annexation', year: 1875, state: 'istren', regions: ['m02-03'], study_case: '' }
	];
	const historyCase: RawEvent[] = [{ kind: 'study_case', year: 1900, label: 'Obrození serenštiny', event_kind: 'revival', spec_event: 4 }];
	const cases = listEvents(worldCases, historyCase, ctx);

	it('událost zadání se štítkem je třídy case a nese štítek jako první údaj karty', () => {
		const tvrda = cases.find((e) => e.index === 0 && e.source === 'author')!;
		expect(tvrda.cls).toBe('case');
		expect(tvrda.caseLabel).toBe('Tvrdá politika Istrenu');
		expect(tvrda.details[0]).toEqual({ term: 'kronika.term.case', value: 'Tvrdá politika Istrenu' });
		expect(tvrda.specEvent).toBeNull();
	});

	it('prázdný štítek znamená obyčejnou událost dějin autora', () => {
		const plain = cases.find((e) => e.index === 1 && e.source === 'author')!;
		expect(plain.cls).toBe('author');
		expect(plain.caseLabel).toBe('');
	});

	it('studijní případ běhu má nadpis z label a odkaz na událost zadání (spec_event)', () => {
		const run = cases.find((e) => e.source === 'history')!;
		expect(run).toMatchObject({ cls: 'case', kindLabel: 'kronika.kind.study_case', title: 'Obrození serenštiny', caseLabel: 'Obrození serenštiny', specEvent: 4 });
	});

	it('filtr případů skryje jen případy; obyčejná událost zůstane', () => {
		const shown = filterEvents(cases, { show: { author: true, soc: true, lang: true, case: false }, query: '' });
		expect(shown.map((e) => e.key)).toEqual(['a1']);
	});

	it('případ a obyčejná událost stejného roku a druhu se nesloučí do jednoho řádku', () => {
		const rows = mergeRows(cases.filter((e) => e.source === 'author'));
		expect(rows.filter((r) => r.kind === 'annexation').map((r) => [r.cls, r.count])).toEqual([
			['case', 1],
			['author', 1]
		]);
	});
});

describe('kronika: rozpis drobných změn', () => {
	it('druhy s nulovým počtem nejsou; neznámý druh zůstane jako text', () => {
		const out = kindCounts({ innovation: 0, analogy: 4, mystery: 2 }, tr);
		expect(out.map((k) => [k.kind, k.value])).toEqual([
			['analogy', 4],
			['mystery', 2]
		]);
		expect(out[1].label).toBe('mystery');
		expect(out.every((k) => k.why === '')).toBe(true);
	});

	it('shodný počet se řadí podle názvu druhu, prázdný vstup dá prázdný rozpis', () => {
		expect(kindCounts({ state: 1, annexation: 1 }, tr).map((k) => k.kind)).toEqual(['annexation', 'state']);
		expect(kindCounts(undefined, tr)).toEqual([]);
	});
});

describe('kronika: století a souhrn', () => {
	const summary = {
		'1800': { phonologized: 20, established: 7, analogy: 3, stress_rule_changed: 2, stress_strength_changed: 1, innovation: 0 },
		'1900': { grammaticalized: 4, exapted: 1, extinct: 5 }
	};

	it('souhrn sčítá zvuk (established + phonologized) a přízvuk, nuly vynechá', () => {
		const rows = mergeRows(listEvents(world, history, ctx));
		const blocks = centuries(-700, 1950, summary, rows, tr);
		const c1800 = blocks.find((c) => c.key === 1800)!;
		expect(c1800.summary).toEqual([
			{ id: 'sound', value: 27 },
			{ id: 'stress', value: 3 },
			{ id: 'analogy', value: 3 }
		]);
		expect(c1800.rows.length).toBe(4);
		expect(blocks.find((c) => c.key === 1900)!.summary.map((s) => s.id)).toEqual(['grammar', 'extinct']);
	});

	it('rozpis století jde od nejčastějšího druhu, milníky a uzavřené procesy jsou poslední s vysvětlením', () => {
		const mixed = {
			'1800': { milestone: 9, process_closed: 2, phonologized: 20, established: 7, analogy: 3, stress_rule_changed: 2, innovation: 0 }
		};
		const c = centuries(-700, 1950, mixed, [], tr).find((b) => b.key === 1800)!;
		expect(c.kinds.map((k) => k.kind)).toEqual(['phonologized', 'established', 'analogy', 'stress_rule_changed', 'milestone', 'process_closed']);
		expect(c.kinds.at(-2)).toMatchObject({ label: 'kronika.kind.milestone', value: 9, why: 'kronika.why.milestone' });
		expect(c.kinds.at(-1)).toMatchObject({ label: 'kronika.kind.process_closed', value: 2, why: 'kronika.why.process_closed' });
	});

	it('rozsah od začátku do konce běhu, poslední století končí koncem běhu', () => {
		const blocks = centuries(-700, 1950, undefined, [], tr);
		expect(blocks[0]).toMatchObject({ key: -700, from: -700, to: -601 });
		expect(blocks.at(-1)).toMatchObject({ key: 1900, from: 1900, to: 1950 });
		expect(blocks.length).toBe(27);
	});
});
