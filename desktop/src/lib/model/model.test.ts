import { describe, expect, it } from 'vitest';
import { fmt, isChanged, lead, same, stepFor, tableView, valueOf, withCell } from './model';

const item = { name: 'leveling_rate', kind: 'number', default: 0.35 };

describe('model', () => {
	it('hodnota světa přepíše výchozí a změna se pozná', () => {
		expect(valueOf(item, { leveling_rate: 0.8 })).toBe(0.8);
		expect(valueOf(item, {})).toBe(0.35);
		expect(isChanged(item, { leveling_rate: 0.8 })).toBe(true);
		expect(isChanged(item, { leveling_rate: 0.35 })).toBe(false);
	});
	it('porovnává tabulky do hloubky', () => {
		expect(same({ a: { x: 1 } }, { a: { x: 1 } })).toBe(true);
		expect(same({ a: { x: 1 } }, { a: { x: 2 } })).toBe(false);
	});
	it('tabulka na řádky a sloupce', () => {
		expect(tableView({ a: { x: 1, y: 2 }, b: { x: 3 } })).toEqual({ head: ['x', 'y'], rows: [{ key: 'a', cells: [1, 2] }, { key: 'b', cells: [3, undefined] }] });
		expect(tableView({})).toBeNull();
	});
	it('změna buňky nemění původní hodnotu', () => {
		const src = { a: { x: 1 } };
		expect(withCell(src, ['a', 'x'], 5)).toEqual({ a: { x: 5 } });
		expect(src.a.x).toBe(1);
	});
	it('formát a krok', () => {
		expect(fmt(0.8, 'cs')).toBe('0,80');
		expect(fmt(6, 'cs')).toBe('6');
		expect(stepFor(0, 1)).toBe(0.05);
		expect(stepFor(0, 50)).toBe(0.5);
	});
	it('první věta', () => {
		expect(lead('Jedna věta. Druhá věta.')).toEqual({ short: 'Jedna věta.', cut: true });
		expect(lead('Podle centra (dok. 27): skupina přebírá. Další věta.').short).toBe('Podle centra (dok. 27): skupina přebírá.');
	});
});
