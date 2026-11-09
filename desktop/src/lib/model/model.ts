// Obrazovka Model: výpočty nad schématem parametrů enginu a hodnotami světa (bez UI).
import type { ParameterSchema } from '../engine';

export type ParamItem = ParameterSchema['items'][number];
export type Overrides = Record<string, unknown> | undefined;

/** Hluboké porovnání hodnot parametrů (čísla, tabulky). */
export function same(a: unknown, b: unknown): boolean {
	if (typeof a === 'number' && typeof b === 'number') return Math.abs(a - b) < 1e-9;
	if (a && b && typeof a === 'object' && typeof b === 'object') {
		const ka = Object.keys(a as object);
		const kb = Object.keys(b as object);
		return ka.length === kb.length && ka.every((k) => same((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]));
	}
	return a === b;
}

/** Hodnota ve světě, jinak výchozí z enginu. */
export function valueOf(item: ParamItem, overrides: Overrides): unknown {
	return overrides && item.name in overrides ? overrides[item.name] : item.default;
}

/** Svět tenhle parametr přepisuje a hodnota se liší od výchozí. */
export function isChanged(item: ParamItem, overrides: Overrides): boolean {
	return !!overrides && item.name in overrides && !same(overrides[item.name], item.default);
}

export function changedIn(items: ParamItem[], overrides: Overrides): ParamItem[] {
	return items.filter((i) => isChanged(i, overrides));
}

/** Parametry světa, které schéma nezná (starší nebo cizí zadání). */
export function unknownKeys(schemaItems: ParamItem[][], overrides: Overrides): string[] {
	const known = new Set(schemaItems.flat().map((i) => i.name));
	return Object.keys(overrides ?? {}).filter((k) => !known.has(k));
}

/** Krok posuvníku z rozsahu. */
export function stepFor(min: number, max: number): number {
	const span = max - min;
	if (span <= 1) return 0.05;
	if (span <= 5) return 0.1;
	if (span <= 10) return 0.25;
	if (span <= 50) return 0.5;
	return 1;
}

export function roundTo(n: number, step: number): number {
	const digits = Math.max(0, Math.ceil(-Math.log10(step)) + 1);
	return Number(n.toFixed(digits));
}

/** Číslo pro zobrazení: bez zbytečných nul, s desetinnou čárkou podle jazyka. */
export function fmt(n: unknown, locale: 'cs' | 'en'): string {
	if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
	return n.toLocaleString(locale === 'cs' ? 'cs-CZ' : 'en-GB', { maximumFractionDigits: 3, minimumFractionDigits: Number.isInteger(n) ? 0 : 2 });
}

/** První věta popisu (nejvýš `max` znaků), zbytek je za „Celý popis“. */
export function lead(text: string, max = 190): { short: string; cut: boolean } {
	const clean = text.replace(/`+/g, '').replace(/\s+/g, ' ').trim();
	const m = clean.match(/^.*?[.!?](?=\s+\p{Lu}|$)/u);
	let short = m ? m[0] : clean;
	if (short.length > max) short = short.slice(0, max).replace(/\s+\S*$/, '') + '…';
	return { short, cut: short.length < clean.length };
}

export interface TableView {
	head: string[];
	rows: { key: string; cells: unknown[] }[];
}

/** Tabulková hodnota jako řádky a sloupce: {a: 1} -> jeden sloupec, {a: {x: 1}} -> sloupce x. */
export function tableView(value: unknown): TableView | null {
	if (!value || typeof value !== 'object') return null;
	const entries = Object.entries(value as Record<string, unknown>);
	if (!entries.length) return null;
	if (entries.every(([, v]) => v && typeof v === 'object')) {
		const head: string[] = [];
		for (const [, v] of entries) for (const k of Object.keys(v as object)) if (!head.includes(k)) head.push(k);
		return { head, rows: entries.map(([key, v]) => ({ key, cells: head.map((h) => (v as Record<string, unknown>)[h]) })) };
	}
	return { head: [''], rows: entries.map(([key, v]) => ({ key, cells: [v] })) };
}

/** Kopie hodnoty s jednou změněnou buňkou (cesta o 1 nebo 2 klíčích). */
export function withCell(value: unknown, path: string[], next: number): Record<string, unknown> {
	const copy = JSON.parse(JSON.stringify(value ?? {})) as Record<string, unknown>;
	if (path.length === 1) copy[path[0]] = next;
	else {
		const inner = (copy[path[0]] ?? {}) as Record<string, unknown>;
		inner[path[1]] = next;
		copy[path[0]] = inner;
	}
	return copy;
}

/** Slovní úrovně tabulky (kind level_table / level_table2). */
export const isLevelTable = (item: ParamItem) => item.kind === 'level_table' || item.kind === 'level_table2';
