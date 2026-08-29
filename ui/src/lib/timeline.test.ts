import { describe, expect, it } from 'vitest';
import {
	advanceSnapshot,
	findEdgeBetween,
	newEdgeFields,
	propagateSnapshots,
	retypeEdge,
	snapshotForCanvas,
	stampBornYears
} from './timeline';
import type { SnapshotsByYear, TLEdge, TLNode } from './timeline';

function node(id: string, year: number, extra: Partial<TLNode['data']> = {}): TLNode {
	return { id, type: 'language', position: { x: 0, y: 0 }, data: { label: id, year, ...extra } };
}

function edge(
	id: string,
	source: string,
	target: string,
	year: number,
	type: string | undefined = undefined
): TLEdge {
	return { id, source, target, type, data: { year } };
}

describe('pravidlo 1: kontakt vytvořený v jednom roce zůstává kontaktem', () => {
	it('kontaktní hrana projde další rok beze změny typu', () => {
		const current = {
			nodes: [node('a', 0), node('b', 0)],
			edges: [edge('e1', 'a', 'b', 0, 'contact')]
		};

		const next = advanceSnapshot(current, undefined, 0);

		expect(next.edges).toHaveLength(1);
		expect(next.edges[0].type).toBe('contact');
	});

	it('zůstává kontaktem i po víc krocích v řadě', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] }
		};

		propagateSnapshots(snapshots, [0, 100, 200, 300]);

		for (const year of [100, 200, 300]) {
			expect(snapshots[year].edges).toHaveLength(1);
			expect(snapshots[year].edges[0].type).toBe('contact');
			expect(snapshots[year].edges[0].id).toBe('e1');
		}
	});

	it('nepřepisuje vlastní data kontaktu (intenzitu, typ vztahu) při každém kroku', () => {
		const snapshots: SnapshotsByYear = {
			0: {
				nodes: [node('a', 0), node('b', 0)],
				edges: [
					{
						id: 'e1',
						source: 'a',
						target: 'b',
						type: 'contact',
						data: { year: 0, contactType: 'war', intensity: 90, direction: 'ba' }
					}
				]
			}
		};

		propagateSnapshots(snapshots, [0, 100]);

		expect(snapshots[100].edges[0].data).toMatchObject({
			contactType: 'war',
			intensity: 90,
			direction: 'ba'
		});
	});
});

describe('pravidlo 2: dědičnost vytvořená v jednom roce se v dalším stává kontaktem', () => {
	it('hrana bez type (dědičnost) se v dalším roce stane kontaktem', () => {
		const current = {
			nodes: [node('proto', 0), node('child', 0)],
			edges: [edge('e1', 'proto', 'child', 0)] // type undefined = dědičnost
		};

		const next = advanceSnapshot(current, undefined, 0);

		expect(next.edges).toHaveLength(1);
		expect(next.edges[0].type).toBe('contact');
	});

	it('v roce svého vzniku ZŮSTÁVÁ dědičností — konverze se týká jen dalšího kroku', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('proto', 0), node('child', 0)], edges: [edge('e1', 'proto', 'child', 0)] }
		};

		propagateSnapshots(snapshots, [0, 100]);

		expect(snapshots[0].edges[0].type).toBeUndefined();
		expect(snapshots[100].edges[0].type).toBe('contact');
	});

	it('jednou zkonvertovaná na kontakt už zpátky na dědičnost nepřejde', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('proto', 0), node('child', 0)], edges: [edge('e1', 'proto', 'child', 0)] }
		};

		propagateSnapshots(snapshots, [0, 100, 200]);

		expect(snapshots[100].edges[0].type).toBe('contact');
		expect(snapshots[200].edges[0].type).toBe('contact');
	});
});

describe('pravidlo 3: mazání se kaskádovitě promítá do všech dalších let', () => {
	it('smazaná hrana zmizí i z bezprostředně dalšího roku', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			100: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] }
		};

		// Uživatel smaže hranu v roce 0 (edituje aktuální rok přímo).
		snapshots[0].edges = [];

		propagateSnapshots(snapshots, [0, 100, 200]);

		expect(snapshots[100].edges).toHaveLength(0);
		expect(snapshots[200].edges).toHaveLength(0);
	});

	it('mazání se propaguje přes VÍCE než jeden krok dopředu', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			100: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			200: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			300: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] }
		};

		snapshots[0].edges = [];
		propagateSnapshots(snapshots, [0, 100, 200, 300]);

		expect(snapshots[100].edges).toHaveLength(0);
		expect(snapshots[200].edges).toHaveLength(0);
		expect(snapshots[300].edges).toHaveLength(0);
	});

	it('hrana vzniklá AŽ PO roku mazání zůstává nedotčená', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			100: { nodes: [node('a', 0), node('b', 0)], edges: [] }
		};

		// Nová hrana vznikne v roce 100, po smazání té staré v roce 0.
		snapshots[0].edges = [];
		snapshots[100].edges = [edge('e2', 'a', 'b', 100, 'contact')];

		propagateSnapshots(snapshots, [0, 100, 200]);

		expect(snapshots[200].edges.map((e) => e.id)).toEqual(['e2']);
	});

	it('smazaný uzel se kaskádovitě odstraní i se svými hranami', () => {
		const snapshots: SnapshotsByYear = {
			0: {
				nodes: [node('a', 0), node('b', 0)],
				edges: [edge('e1', 'a', 'b', 0, 'contact')]
			},
			100: {
				nodes: [node('a', 0), node('b', 0)],
				edges: [edge('e1', 'a', 'b', 0, 'contact')]
			}
		};

		snapshots[0].nodes = snapshots[0].nodes.filter((n) => n.id !== 'b');
		snapshots[0].edges = [];

		propagateSnapshots(snapshots, [0, 100, 200]);

		expect(snapshots[200].nodes.map((n) => n.id)).toEqual(['a']);
		expect(snapshots[200].edges).toHaveLength(0);
	});
});

describe('pravidlo 4: tombstone odstraní všechny hrany mrtvého jazyka', () => {
	it('hrany dotýkající se mrtvého uzlu se do dalšího roku nepřenesou', () => {
		const current = {
			nodes: [node('a', 0), node('b', 0, { isDead: true }), node('c', 0)],
			edges: [edge('e1', 'a', 'b', 0, 'contact'), edge('e2', 'b', 'c', 0, 'contact')]
		};

		const next = advanceSnapshot(current, undefined, 0);

		expect(next.edges).toHaveLength(0);
	});

	it('nedotčené hrany mezi živými uzly přežijí', () => {
		const current = {
			nodes: [node('a', 0), node('b', 0, { isDead: true }), node('c', 0)],
			edges: [
				edge('e1', 'a', 'b', 0, 'contact'),
				edge('e2', 'a', 'c', 0, 'contact')
			]
		};

		const next = advanceSnapshot(current, undefined, 0);

		expect(next.edges.map((e) => e.id)).toEqual(['e2']);
	});

	it('jednou mrtvý zůstává mrtvý — hrany se neobjeví ani o víc let dál', () => {
		const snapshots: SnapshotsByYear = {
			0: {
				nodes: [node('a', 0), node('b', 0, { isDead: true })],
				edges: []
			}
		};

		propagateSnapshots(snapshots, [0, 100, 200, 300]);

		for (const year of [100, 200, 300]) {
			expect(snapshots[year].nodes.find((n) => n.id === 'b')?.data?.isDead).toBe(true);
			expect(snapshots[year].edges).toHaveLength(0);
		}
	});

	it('úprava udělaná přímo v pozdějším roce PŘEŽIJE cascade z fromYear', () => {
		// Bez fromYear by tenhle test spadl: cascade by rok 100 přepočítala od
		// nuly a přepsala by ho zpět na "Původní" — přesně bug, který tenhle
		// parametr řeší (jakákoli editace přímo v pozdějším roce, tombstone
		// nevyjímaje, by se vzápětí sama vzala zpět).
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0, { label: 'Původní' } as any)], edges: [] },
			100: { nodes: [node('a', 0, { label: 'PŘEJMENOVÁNO' } as any)], edges: [] }
		};

		propagateSnapshots(snapshots, [0, 100, 200], 100);

		expect((snapshots[100].nodes[0].data as any).label).toBe('PŘEJMENOVÁNO');
		expect((snapshots[200].nodes[0].data as any).label).toBe('PŘEJMENOVÁNO');
		// Rok 0 zůstává, jak byl — propagace z 100 do něj nesahá zpátky.
		expect((snapshots[0].nodes[0].data as any).label).toBe('Původní');
	});

	it('tombstone zapnutý V ROCE Y odřízne hrany od roku Y dál, ale předchozí roky nechá být', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0), node('b', 0)], edges: [edge('e1', 'a', 'b', 0, 'contact')] },
			100: {
				nodes: [node('a', 0), node('b', 0, { isDead: true })],
				// Simuluje setDead() z +page.svelte: hrany se v CURRENT roce
				// odeberou hned, ne až propagací.
				edges: []
			}
		};

		// V aplikaci se editace vždy propaguje jen z právě zobrazeného roku
		// (fromYear = 100) — ne od nuly, jinak by rok 100 dostal zpátky
		// hranu zděděnou z roku 0 dřív, než se stihne uplatnit tombstone.
		propagateSnapshots(snapshots, [0, 100, 200], 100);

		// Minulost (rok 0) se retroaktivně nemění.
		expect(snapshots[0].edges).toHaveLength(1);
		// Od roku 100 dál (kdy byl jazyk označen mrtvým) žádné spojení není.
		expect(snapshots[100].edges).toHaveLength(0);
		expect(snapshots[200].edges).toHaveLength(0);
	});

	it('tombstone a dědičnost->kontakt konverze spolu nekolidují', () => {
		// Hrana je v roce 0 dědičnost; ve stejném roce se uzel označí mrtvým.
		const current = {
			nodes: [node('proto', 0), node('child', 0, { isDead: true })],
			edges: [edge('e1', 'proto', 'child', 0)]
		};

		const next = advanceSnapshot(current, undefined, 0);

		// Tombstone má přednost — hrana se nepřevede na kontakt, prostě zmizí.
		expect(next.edges).toHaveLength(0);
	});
});

describe('mutace na místě (bezpečnost proti nekonečné smyčce)', () => {
	it('propagateSnapshots nikdy nepřepíše objekt aktuálně zpracovávaného roku', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0)], edges: [] },
			100: { nodes: [node('a', 0)], edges: [] }
		};
		const originalYear0Ref = snapshots[0];
		const originalYear100Ref = snapshots[100];

		propagateSnapshots(snapshots, [0, 100]);

		// Objekt roku 0 (poslední v řetězu jako "next") se nikdy nezpracovává
		// jako `nextYear` cíl zápisu -> reference zůstává stejná.
		expect(snapshots[0]).toBe(originalYear0Ref);
		// Rok 100 JE cíl zápisu, ale mutuje se STEJNÝ objekt (jen .nodes/.edges
		// se přepíšou), ne nahrazení celého záznamu novým objektem.
		expect(snapshots[100]).toBe(originalYear100Ref);
	});

	it('nový rok, který ještě neexistoval, se vytvoří', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [node('a', 0)], edges: [] }
		};

		propagateSnapshots(snapshots, [0, 500]);

		expect(snapshots[500]).toBeDefined();
		expect(snapshots[500].nodes.map((n) => n.id)).toEqual(['a']);
	});
});

describe('stampBornYears', () => {
	it('doplní chybějící rok narození podle prvního výskytu', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [{ id: 'a', data: {} }], edges: [] },
			100: { nodes: [{ id: 'a', data: {} }, { id: 'b', data: {} }], edges: [] }
		};

		stampBornYears(snapshots, [0, 100]);

		expect(snapshots[0].nodes[0].data?.year).toBe(0);
		expect(snapshots[100].nodes[0].data?.year).toBe(0); // 'a' se poprvé objevil v roce 0
		expect(snapshots[100].nodes[1].data?.year).toBe(100); // 'b' až tady
	});

	it('nepřepisuje už existující rok narození', () => {
		const snapshots: SnapshotsByYear = {
			0: { nodes: [], edges: [] },
			100: { nodes: [node('a', 50)], edges: [] } // vzniklo "uprostřed", data.year=50
		};

		stampBornYears(snapshots, [0, 100]);

		expect(snapshots[100].nodes[0].data?.year).toBe(50);
	});
});

describe('kreslení hrany: tlačítko Kontakt musí opravdu přepnout typ', () => {
	// xyflow rozezná duplicitní spojení jen podle source/target (ne podle
	// type), takže addEdge() z knihovny tiše zahodí pokus nakreslit kontakt
	// tam, kde už dědičnost existuje. Uživatel nahlásil přesně tohle: hrana
	// vypadá (a je) pořád jako dědičnost, i po přepnutí na nástroj Kontakt.

	it('findEdgeBetween najde existující hranu mezi dvojicí uzlů', () => {
		const edges = [edge('e1', 'a', 'b', 0)];
		expect(findEdgeBetween(edges, 'a', 'b')).toBe(0);
		expect(findEdgeBetween(edges, 'b', 'a')).toBe(-1); // směr se počítá
		expect(findEdgeBetween(edges, 'a', 'c')).toBe(-1);
	});

	it('přetažení Kontaktu nad existující dědičností ji PŘETYPUJE, ne ignoruje', () => {
		const dedicnost = edge('e1', 'a', 'b', 0); // starší projekt: type undefined
		const vysledek = retypeEdge(dedicnost, true, 100);

		expect(vysledek.type).toBe('contact');
		expect(vysledek.id).toBe('e1'); // stejná hrana, jen jiný typ — ne nová
		expect(vysledek.data).toMatchObject({ contactType: 'neighborhood', intensity: 50, direction: 'ab' });
	});

	it('přetažení Dědičnosti nad existujícím kontaktem ji vrátí zpět na dědičnost', () => {
		const kontakt = edge('e1', 'a', 'b', 0, 'contact');
		const vysledek = retypeEdge(kontakt, false, 100);

		expect(vysledek.type).toBe('straight');
		expect(vysledek.animated).toBeUndefined();
	});

	it('přepnutí tam a zpátky zachová vlastní data kontaktu (typ vztahu, intenzitu)', () => {
		const puvodni: TLEdge = {
			id: 'e1',
			source: 'a',
			target: 'b',
			type: 'contact',
			data: { year: 0, contactType: 'war', intensity: 90, direction: 'ba' }
		};

		const naDedicnost = retypeEdge(puvodni, false, 100);
		const zpatkyNaKontakt = retypeEdge(naDedicnost, true, 200);

		expect(zpatkyNaKontakt.data).toMatchObject({ contactType: 'war', intensity: 90, direction: 'ba' });
	});

	it('newEdgeFields pro Kontakt dá type: contact a výchozí data', () => {
		expect(newEdgeFields(true, 100)).toMatchObject({
			type: 'contact',
			data: { contactType: 'neighborhood', intensity: 50, direction: 'ab', year: 100 }
		});
	});

	it('newEdgeFields pro Dědičnost dá explicitní přímý renderer', () => {
		const fields = newEdgeFields(false, 100);
		expect(fields.type).toBe('straight');
		expect(fields.data).toEqual({ year: 100 });
	});

	it('snapshot pro plátno normalizuje starou dědičnost a nevrací zdrojové reference', () => {
		const snapshot = { nodes: [node('a', 0)], edges: [edge('e1', 'a', 'b', 0)] };
		const canvas = snapshotForCanvas(snapshot, 100);

		expect(canvas.edges[0].type).toBe('straight');
		canvas.nodes[0].data!.label = 'jen plátno';
		canvas.edges[0].data!.year = 999;
		expect(snapshot.nodes[0].data?.label).toBe('a');
		expect(snapshot.edges[0].data?.year).toBe(0);
	});
});
