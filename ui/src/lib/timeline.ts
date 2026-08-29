/**
 * Čistá logika kaskády časové osy grafového editoru.
 *
 * Vytažená z `map/+page.svelte`, aby šla otestovat nezávisle na Svelte
 * reaktivitě — bez toho by čtyři pravidla níže šlo ověřit jen ručním
 * proklikáním v prohlížeči, a jejich vzájemné interakce (kaskáda přes víc
 * let, tombstone + mazání zároveň) se tak snadno rozbijí při další úpravě.
 *
 * Pravidla (zadání uživatele):
 * 1. Kontakt vytvořený v jednom roce zůstává kontaktem ve všech dalších.
 * 2. Dědičnost vytvořená v jednom roce se v následujícím roce stává
 *    kontaktem — dědičnost je jednorázová událost odštěpení v roce svého
 *    vzniku, ne opakovaně kreslený vztah.
 * 3. Smazání hrany (nebo uzlu) se kaskádovitě promítne do všech
 *    následujících let.
 * 4. Zapnutí tombstone (mrtvý jazyk) odstraní všechny jeho hrany a jazyk už
 *    dál neovlivňuje ostatní — platí od roku, kdy byl označen, dál.
 *
 * Funkce mutují svůj vstup, stejně jako předloha — a to záměrně, ne z
 * lenosti. `propagateSnapshots` píše výhradně do let PO aktuálně editovaném
 * (`nextYear`), nikdy nepřepisuje objekt roku, který se právě edituje.
 * Kdyby místo toho vracela celý nový strom a volající ho přiřadil zpět do
 * `projectState.snapshots`, Svelteho reaktivita by referenční změnu uviděla
 * i u právě editovaného roku — a protože je zápis do snapshotu spouštěčem
 * kaskády, druhé přiřazení stejného roku by kaskádu spustilo znovu:
 * nekonečná smyčka efektů. Mutace na místě je tu bezpečnostní vlastnost,
 * ne implementační detail.
 */

export type TLNodeData = {
	year?: number;
	isDead?: boolean;
	[key: string]: unknown;
};

export type TLEdgeData = {
	year?: number;
	[key: string]: unknown;
};

export type TLNode = {
	id: string;
	data?: TLNodeData;
	[key: string]: unknown;
};

export type TLEdge = {
	id: string;
	source: string;
	target: string;
	type?: string;
	animated?: boolean;
	data?: TLEdgeData;
	[key: string]: unknown;
};

export type YearSnapshot = { nodes: TLNode[]; edges: TLEdge[] };
export type SnapshotsByYear = Record<number, YearSnapshot>;

function clone<T>(value: T): T {
	return JSON.parse(JSON.stringify(value));
}

/**
 * Připraví uložený snapshot pro xyflow.
 *
 * Snapshoty jsou zdroj pravdy projektu; editor ale při tažení a při
 * připojování uzlů upravuje objekty, které dostane přes `bind:nodes` a
 * `bind:edges`. Vrácení kopií proto není jen kosmetika: bez něj šlo při
 * přepnutí času současně upravit i jiný, právě uložený rok.
 *
 * Staré projekty ukládaly dědičnost jako `type: undefined`. XYFlow pak typ
 * jen domýšlel přes výchozí nastavení, což vedlo k odlišnému vykreslení po
 * načtení a bezprostředně po vytvoření. Dědičnost má odteď explicitní
 * renderer `straight`; pro simulátor to stále znamená dědičnost, protože
 * jediný typ kontaktu je `contact`.
 */
export function snapshotForCanvas(snapshot: YearSnapshot, year: number): YearSnapshot {
	return {
		nodes: clone(snapshot.nodes),
		edges: snapshot.edges.map((edge) => ({
			...clone(edge),
			type: edge.type === 'contact' ? 'contact' : 'straight',
			data: { ...clone(edge.data ?? {}), year: edge.data?.year ?? year }
		}))
	};
}

/**
 * Zafixuje "rok narození" (`data.year`) uzlů a hran podle jejich prvního
 * výskytu na ose. Migrace pro projekty založené předtím, než se `year`
 * začal používat jako kotva pro kaskádu — bez ní by se starší hrany při
 * propagaci ztrácely nebo naopak nemazaly.
 *
 * Mutuje `snapshots` na místě.
 */
export function stampBornYears(snapshots: SnapshotsByYear, years: number[]): void {
	const seenNodeYears = new Map<string, number>();
	const seenEdgeYears = new Map<string, number>();

	for (const year of years) {
		const snap = snapshots[year];
		if (!snap) continue;

		for (const node of snap.nodes) {
			if (!seenNodeYears.has(node.id)) {
				seenNodeYears.set(node.id, node.data?.year ?? year);
			}
			if (!node.data) node.data = {};
			node.data.year = seenNodeYears.get(node.id);
		}

		for (const edge of snap.edges) {
			if (!seenEdgeYears.has(edge.id)) {
				seenEdgeYears.set(edge.id, edge.data?.year ?? year);
			}
			if (!edge.data) edge.data = {};
			edge.data.year = seenEdgeYears.get(edge.id);
		}
	}
}

/**
 * Odvodí obsah roku `nextYear` z roku `currentYear`. Nemutuje vstupy, vrací
 * novou dvojici `{ nodes, edges }`, kterou má volající zapsat do
 * `nextYear`ova záznamu — sama o sobě do `snapshots` nezasahuje.
 */
export function advanceSnapshot(
	current: YearSnapshot,
	next: YearSnapshot | undefined,
	currentYear: number
): YearSnapshot {
	const currentNodes = clone(current.nodes);
	const currentEdges = clone(current.edges);
	const newNextNodes = clone(next?.nodes ?? []);

	// 1. Zkopírovat nebo aktualizovat uzly z aktuálního roku.
	for (const node of currentNodes) {
		const existingIdx = newNextNodes.findIndex((n) => n.id === node.id);
		if (existingIdx !== -1) {
			newNextNodes[existingIdx] = node;
		} else {
			newNextNodes.push(node);
		}
	}

	// 2. Smazat uzly, které vznikly v <= currentYear, ale v aktuálním roce
	//    už nejsou (byly smazány) — pravidlo 3, kaskáda mazání pro uzly.
	for (let j = newNextNodes.length - 1; j >= 0; j--) {
		const n = newNextNodes[j];
		const bornYear = n.data?.year ?? 0;
		if (bornYear <= currentYear && !currentNodes.find((cn) => cn.id === n.id)) {
			newNextNodes.splice(j, 1);
		}
	}

	// Tombstone (pravidlo 4): mrtvý jazyk už neovlivňuje ostatní. `isDead`
	// je součástí uzlu, takže jednou mrtvý zůstává mrtvý ve všech dalších
	// letech automaticky (kopíruje/přepisuje se vpřed spolu s uzlem v kroku 1).
	const deadNodeIds = new Set(currentNodes.filter((n) => n.data?.isDead).map((n) => n.id));
	const touchesDead = (e: TLEdge) => deadNodeIds.has(e.source) || deadNodeIds.has(e.target);

	const newNextEdges = clone(next?.edges ?? []);

	// 3. Zkopírovat hrany z aktuálního roku, s konverzí dědičnosti na
	//    kontakt (pravidla 1 a 2), a bez hran mrtvého uzlu (pravidlo 4).
	for (const edge of currentEdges) {
		if (touchesDead(edge)) continue;

		const existingIdx = newNextEdges.findIndex((e) => e.id === edge.id);
		const newEdge: TLEdge = { ...edge };

		if (newEdge.type !== 'contact') {
			newEdge.type = 'contact';
			newEdge.animated = false;
			newEdge.data = {
				...newEdge.data,
				contactType: 'neighborhood',
				intensity: 50,
				direction: 'ab'
			};
		}

		if (existingIdx !== -1) {
			newNextEdges[existingIdx] = newEdge;
		} else {
			newNextEdges.push(newEdge);
		}
	}

	// 4. Smazat hrany na neexistující/mrtvé uzly, nebo hrany smazané
	//    v aktuálním roce — kaskáda mazání pro hrany (pravidlo 3).
	for (let j = newNextEdges.length - 1; j >= 0; j--) {
		const e = newNextEdges[j];
		const sourceExists = newNextNodes.some((n) => n.id === e.source);
		const targetExists = newNextNodes.some((n) => n.id === e.target);

		if (!sourceExists || !targetExists || touchesDead(e)) {
			newNextEdges.splice(j, 1);
			continue;
		}

		const bornYear = e.data?.year ?? 0;
		if (bornYear <= currentYear && !currentEdges.find((ce) => ce.id === e.id)) {
			newNextEdges.splice(j, 1);
		}
	}

	return { nodes: newNextNodes, edges: newNextEdges };
}

/**
 * Promítne kaskádu dopředu, od `fromYear` (výchozí: nejstarší rok osy) až po
 * nejnovější. Mutuje `snapshots` na místě — viz vysvětlení nahoře, proč je
 * to záměrné.
 *
 * `snapshots[currentYear]` se během běhu nikdy nepřepisuje, jen se z něj
 * čte; zapisuje se výhradně do `snapshots[nextYear]`, a to buď vytvořením
 * nového objektu (pokud rok ještě neexistoval), nebo přepsáním `.nodes` /
 * `.edges` na existujícím objektu (pokud existoval už dřív).
 *
 * `fromYear` je zásadní pro to, aby úprava udělaná přímo v pozdějším roce
 * (přejmenování, tombstone, smazání hrany) přežila. Bez něj by se každé
 * volání vždycky přepočítalo od úplně prvního roku — a protože krok "vezmi
 * uzel z aktuálního roku a přepiš jím stejné ID v dalším roce" nerozlišuje
 * "beze změny zděděné" od "právě ručně upraveného", by nejbližší další
 * propagace (spuštěná po KAŽDÉ úpravě) tichou předchozí verzi vrátila zpět.
 * Editace vždy probíhá jen v jednom, právě zobrazeném roce, takže cascade
 * volaná po úpravě má z `fromYear` = ten rok začínat, ne od nuly.
 *
 * Bez zadání se použije nejstarší rok osy — to chce jen doplnění nově
 * vzniklé mezery v ose (nový bod přidaný uprostřed), kde žádná pozdější
 * ruční úprava není co chránit.
 */
export function propagateSnapshots(
	snapshots: SnapshotsByYear,
	years: number[],
	fromYear?: number
): void {
	if (years.length < 2) return;

	stampBornYears(snapshots, years);

	const startIdx = fromYear === undefined ? 0 : Math.max(0, years.indexOf(fromYear));

	for (let i = startIdx; i < years.length - 1; i++) {
		const currentYear = years[i];
		const nextYear = years[i + 1];

		const currentSnapshot = snapshots[currentYear] ?? { nodes: [], edges: [] };
		let nextSnapshot = snapshots[nextYear];
		if (!nextSnapshot) {
			nextSnapshot = { nodes: [], edges: [] };
			snapshots[nextYear] = nextSnapshot;
		}

		const advanced = advanceSnapshot(currentSnapshot, nextSnapshot, currentYear);
		nextSnapshot.nodes = advanced.nodes;
		nextSnapshot.edges = advanced.edges;
	}
}

// --- Kreslení hrany v editoru ------------------------------------------------

/**
 * Najde index hrany mezi danou dvojicí uzlů v aktuálním roce, pokud existuje.
 *
 * xyflow rozezná duplicitní spojení jen podle `source`/`target` (a handlů),
 * na `type` se vůbec nedívá — `addEdge()` z knihovny by tedy pokus nakreslit
 * kontakt tam, kde už je dědičnost, tiše zahodil, a vypadalo by to, že se
 * "kontakt nepřepnul". Volající proto musí existující hranu zjistit sám
 * a případně ji přetypovat, místo aby spoléhal na `addEdge()`.
 */
export function findEdgeBetween(edges: TLEdge[], source: string, target: string): number {
	return edges.findIndex((e) => e.source === source && e.target === target);
}

/**
 * Přepíše existující hranu na typ odpovídající právě zvolenému nástroji.
 *
 * Vlastní data kontaktu (typ vztahu, intenzita, směr) se při přepnutí TAM
 * i ZPÁTKY zachovávají, pokud už tam nějaká byla — přepnutí z kontaktu na
 * dědičnost a zase zpět nesmí vygumovat, jak byl kontakt nastavený.
 */
export function retypeEdge(edge: TLEdge, wantsContact: boolean, year: number): TLEdge {
	if (wantsContact) {
		return {
			...edge,
			type: 'contact',
			animated: false,
			data: {
				...edge.data,
				contactType: edge.data?.contactType ?? 'neighborhood',
				intensity: edge.data?.intensity ?? 50,
				direction: edge.data?.direction ?? 'ab',
				year: edge.data?.year ?? year
			}
		};
	}

	return {
		...edge,
		type: 'straight',
		animated: undefined,
		// contactType/intensity/direction se NEMAŽOU, jen přestanou být
		// aktivní — dokud typ není `contact`, ContactEdge se nevykresluje
		// a na tahle pole se nikde nesahá. Kdyby se tu `data` nahradilo jen
		// `{ year }`, přepnutí zpět na kontakt by je muselo znovu dohádat
		// z výchozích hodnot.
		data: { ...edge.data, year: edge.data?.year ?? year }
	};
}

/**
 * Data pro zbrusu novou hranu odpovídající právě zvolenému nástroji.
 *
 * Vrací jen `type`/`data` (bez `id`/`source`/`target`) — to už doplní
 * `addEdge()` z xyflow při spojení s objektem `Connection`.
 */
export function newEdgeFields(
	wantsContact: boolean,
	year: number
): Pick<TLEdge, 'type' | 'data'> {
	return wantsContact
		? { type: 'contact', data: { contactType: 'neighborhood', intensity: 50, direction: 'ab', year } }
		: { type: 'straight', data: { year } };
}
