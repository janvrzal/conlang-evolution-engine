import { describe, expect, it } from 'vitest';
import type { ExportV2, FrameV2 } from './export';
import { cell, descendants, extraSegments, MANNERS, newLanguageId, PLACES, regionCount, toggleSegment } from './protojazyky';
import type { WorldSpec } from '$lib/state.svelte';

const world = {
	languages: [{ id: 'a' }, { id: 'proto2' }],
	regions: [{ id: 'r1' }, { id: 'r2', language: 'proto2' }, { id: 'r3', language: 'a' }]
} as unknown as WorldSpec;

describe('inventář', () => {
	it('přepíná hlásku', () => {
		expect(toggleSegment(['p', 't'], 't')).toEqual(['p']);
		expect(toggleSegment(undefined, 'k')).toEqual(['k']);
	});
	it('najde hlásky mimo tabulku', () => {
		expect(extraSegments(['p', 'ǃ'], ['p'])).toEqual(['ǃ']);
	});
	it('buňka je průnik místa a způsobu', () => {
		const labial = PLACES.find((p) => p.id === 'bilabial')!;
		expect(cell(labial, MANNERS.find((m) => m.id === 'stop')!)).toEqual(['p', 'b']);
		expect(cell(labial, MANNERS.find((m) => m.id === 'trill')!)).toEqual([]);
	});
});

describe('zadání', () => {
	it('počítá kraje, kraj bez jazyka patří prvnímu', () => {
		expect(regionCount(world, 'a')).toBe(2);
		expect(regionCount(world, 'proto2')).toBe(1);
	});
	it('vymyslí volné ID', () => {
		expect(newLanguageId(world)).toBe('proto3');
	});
});

describe('potomci', () => {
	it('vybere rodinu a řadí podle mluvčích doma', () => {
		const result = { groups: [{ id: 'g1', domain: 'home' }, { id: 'g2', domain: 'home' }, { id: 'g3', domain: 'public' }] } as unknown as ExportV2;
		const frame = {
			groups: [
				{ id: 'g1', population: 10, observed_language: 'L1', l2_share: 0 },
				{ id: 'g2', population: 30, observed_language: 'L2', l2_share: 0 },
				{ id: 'g3', population: 99, observed_language: 'L1', l2_share: 0 }
			]
		} as unknown as FrameV2;
		const families = new Map([['L1', 0], ['L2', 0], ['L3', 1]]);
		expect(descendants(frame, result, families, 0)).toEqual([{ id: 'L2', speakers: 30 }, { id: 'L1', speakers: 10 }]);
		expect(descendants(null, result, families, 0)).toEqual([]);
	});
});
