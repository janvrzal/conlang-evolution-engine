import { describe, expect, it } from 'vitest';
import type { EngineSchema } from '$lib/engine';
import { arrowsOf, defaultEvent, fieldsOf, highlightOf, insertIndex, laneOf, outcomesOf, resolveRegion, snapYear, statesAt, type WorldEvent } from './dejiny';

const regions = ['m01-01', 'm01-02', 'm03-06', 'm06-03'];
const schema = {
	levels: { policy_levels: ['tolerant', 'promoted', 'enforced'], lingua_franca_levels: ['rare', 'common'] },
	json_schema: {
		$defs: {
			ElitSpec: {
				required: ['year', 'kind', 'from', 'seat'],
				properties: { year: { type: 'number' }, kind: { const: 'elite' }, from: { type: 'string' }, seat: { type: 'string' }, prestige: { type: 'number', default: 2 }, language: { anyOf: [{ type: 'string' }, { type: 'null' }] } }
			},
			PolicySpec: {
				required: ['year', 'kind', 'state', 'policy'],
				properties: { year: { type: 'number' }, kind: { const: 'language_policy' }, state: { type: 'string' }, policy: { type: 'string' } }
			}
		}
	}
} as unknown as EngineSchema;

describe('dějiny', () => {
	it('zařadí druhy do pruhů', () => {
		expect(laneOf('annexation')).toBe('states');
		expect(laneOf('standard')).toBe('society');
		expect(laneOf('elite')).toBe('people');
		expect(laneOf('sound_shift')).toBe('sounds');
	});
	it('přichytí rok na 25 let a do rozsahu', () => {
		expect(snapYear(763, -700, 1950)).toBe(775);
		expect(snapYear(5000, -700, 1950)).toBe(1950);
	});
	it('najde kraj v odkazu enginu', () => {
		expect(resolveRegion('m03-06+m06-03-v0', regions)).toBe('m03-06');
		expect(resolveRegion('xx', regions)).toBeNull();
	});
	it('počítá státy z událostí', () => {
		const events: WorldEvent[] = [
			{ kind: 'state', year: 0, id: 'a', name: 'A', regions: ['m01-01', 'm01-02'] },
			{ kind: 'state', year: 100, id: 'b', name: 'B', regions: ['m01-02'] },
			{ kind: 'annexation', year: 200, state: 'b', regions: ['m03-06'] }
		];
		expect(statesAt(events, 150).map((s) => [s.id, s.regions])).toEqual([['a', ['m01-01']], ['b', ['m01-02']]]);
		expect(statesAt(events, 300).find((s) => s.id === 'b')?.regions).toEqual(['m01-02', 'm03-06']);
	});
	it('zvýrazní kraje a nakreslí šipku elity', () => {
		const ev: WorldEvent = { kind: 'elite', year: 750, from: 'm06-03', seat: 'm03-06', subjects: ['m03-06'] };
		expect(highlightOf(ev, regions, []).sort()).toEqual(['m03-06', 'm06-03']);
		expect(arrowsOf(ev, regions)).toEqual([{ from: 'm06-03', to: 'm03-06', dashed: false }]);
	});
	it('čte pole událostí ze schématu', () => {
		const fields = fieldsOf(schema, 'language_policy');
		expect(fields.map((f) => [f.name, f.kind])).toEqual([['state', 'state'], ['policy', 'level']]);
		expect(fields[1].levels).toEqual(['tolerant', 'promoted', 'enforced']);
		expect(fieldsOf(schema, 'elite').find((f) => f.name === 'language')?.kind).toBe('language');
		expect(fieldsOf(null, 'elite')).toEqual([]);
	});
	it('vyplní povinná pole nové události', () => {
		const ev = defaultEvent(schema, 'elite', 100, { regions, states: [], languages: ['seren'], label: 'x' });
		expect(ev).toEqual({ kind: 'elite', year: 100, from: 'm01-01', seat: 'm01-02' });
	});
	it('vkládá podle roku', () => {
		expect(insertIndex([{ kind: 'a', year: 0 }, { kind: 'a', year: 100 }, { kind: 'a', year: 200 }], 100)).toBe(2);
	});
	it('spáruje událost zadání s událostí enginu', () => {
		const ev: WorldEvent = { kind: 'annexation', year: 750, state: 'tarem', regions: ['m03-06'] };
		const engine = [
			{ kind: 'annexation', year: 750, state: 'tarem', bilingual: ['a', 'b'] },
			{ kind: 'annexation', year: 750, state: 'jiny', bilingual: [] },
			{ kind: 'annexation', year: 850, state: 'tarem', bilingual: [] }
		];
		expect(outcomesOf(ev, engine, regions)).toEqual([{ kind: 'annexation', year: 750, n: 2, name: undefined }]);
	});
});
