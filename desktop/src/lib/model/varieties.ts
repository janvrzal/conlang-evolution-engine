// Malé jazyky jako variety příbuzného jazyka.
//
// Engine počítá jako samostatný jazyk i osadu o pár stech lidech. Pro čtenáře je to „strašně moc
// mini jazyků“, proto se jazyk pod prahem (méně než 1 000 mluvčích doma, nebo jediná skupina)
// ukazuje jako varieta nejbližšího příbuzného většího jazyka: stejná rodina (protojazyk),
// nejmenší jazyková vzdálenost. Vzdálenost je ze slovníku (průměrná normalizovaná editační
// vzdálenost tvarů), bez slovníku ze stromu linií. Přepínač „všechny jazyky“ ukáže stav enginu.
import type { ExportV2, Lineage } from './export';

export const VARIETY_MAX_SPEAKERS = 1000;

export interface Varieties {
	/** malý jazyk → hostitelský (větší příbuzný) jazyk */
	host: Map<string, string>;
	/** jazyky nad prahem (samostatné) */
	major: string[];
	/** malé jazyky bez vhodného hostitele zůstávají samostatné, ale počítají se mezi malé */
	orphans: string[];
}

/** Levenshteinova vzdálenost dvou řetězců podle znaků (IPA), normalizovaná na 0–1. */
export function formDistance(a: string, b: string): number {
	if (a === b) return 0;
	const x = [...a], y = [...b];
	if (!x.length || !y.length) return 1;
	let prev = Array.from({ length: y.length + 1 }, (_, j) => j);
	for (let i = 1; i <= x.length; i++) {
		const row = [i];
		for (let j = 1; j <= y.length; j++) row[j] = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (x[i - 1] === y[j - 1] ? 0 : 1));
		prev = row;
	}
	return prev[y.length] / Math.max(x.length, y.length);
}

/** Počet kroků ve stromu linií ke společnému předkovi (Infinity, když žádný není). */
export function treeDistance(a: string, b: string, parent: Map<string, string | null>): number {
	const up = (id: string) => {
		const out = new Map<string, number>();
		let cur: string | null | undefined = id, d = 0;
		while (cur && !out.has(cur)) {
			out.set(cur, d++);
			cur = parent.get(cur);
		}
		return out;
	};
	const ua = up(a);
	let cur: string | null | undefined = b, d = 0;
	while (cur) {
		if (ua.has(cur)) return ua.get(cur)! + d;
		cur = parent.get(cur);
		d++;
	}
	return Infinity;
}

/**
 * Rozdělí živé jazyky na samostatné a malé variety.
 * @param speakers linie → mluvčí doma
 * @param groups linie → počet domácích skupin
 * @param family linie → rodina (index protojazyka)
 * @param lexicalDistance volitelně vzdálenost ze slovníku (0–1); jinak strom linií
 */
export function groupVarieties(
	speakers: Map<string, number>,
	groups: Map<string, number>,
	family: Map<string, number>,
	lineages: Pick<Lineage, 'id' | 'parent'>[],
	lexicalDistance?: (a: string, b: string) => number | null
): Varieties {
	const parent = new Map(lineages.map((l) => [l.id, l.parent]));
	const alive = [...speakers.keys()].filter((id) => (speakers.get(id) ?? 0) > 0);
	const small = (id: string) => (speakers.get(id) ?? 0) < VARIETY_MAX_SPEAKERS || (groups.get(id) ?? 0) <= 1;
	const major = alive.filter((id) => !small(id));
	const host = new Map<string, string>();
	const orphans: string[] = [];
	for (const id of alive.filter(small)) {
		const candidates = major.filter((m) => family.get(m) === family.get(id));
		let best: string | null = null, score = Infinity;
		for (const m of candidates) {
			const lex = lexicalDistance?.(id, m);
			// slovník rozhoduje; strom jen jako slabé dorovnání (a náhrada bez slovníku).
			// Linie s jiným kořenem (rodina se rozpadla už na startu) mají strom „daleko“, ne nekonečně.
			const tree = Math.min(treeDistance(id, m, parent), 100);
			const s = lex != null ? lex + tree * 1e-3 : tree;
			if (s < score || (s === score && best && (speakers.get(m) ?? 0) > (speakers.get(best) ?? 0))) [best, score] = [m, s];
		}
		if (best) host.set(id, best);
		else orphans.push(id);
	}
	return { host, major, orphans };
}

/** Vzdálenost jazyků ze slovníku koncového exportu: tvary největší domácí skupiny každé linie. */
export function lexicalDistanceFrom(result: ExportV2): (a: string, b: string) => number | null {
	const best = new Map<string, { id: string; population: number }>();
	for (const g of result.groups) {
		if (g.domain !== 'home' || !g.observed_language) continue;
		const cur = best.get(g.observed_language);
		if (!cur || g.population > cur.population) best.set(g.observed_language, { id: g.id, population: g.population });
	}
	const cache = new Map<string, number | null>();
	return (a, b) => {
		const key = a < b ? `${a}|${b}` : `${b}|${a}`;
		if (cache.has(key)) return cache.get(key)!;
		const la = result.lexicon[best.get(a)?.id ?? ''], lb = result.lexicon[best.get(b)?.id ?? ''];
		let value: number | null = null;
		if (la && lb) {
			let sum = 0, n = 0;
			for (const c of Object.keys(la)) if (lb[c]) (sum += formDistance(la[c].form, lb[c].form)), n++;
			value = n ? sum / n : null;
		}
		cache.set(key, value);
		return value;
	};
}
