import { describe, expect, it } from 'vitest';
import { pointRadius, pointToPercent, pointToPixels, visibleWorldPoints } from './renderer';
import type { WorldMapDocument, WorldMapPoint } from './types';

const document: WorldMapDocument = { name: 'Test', width: 1000, height: 500 };
const point = (id: string, x: number, kind: WorldMapPoint['kind'] = 'language'): WorldMapPoint => ({ id, label: id, x, y: 20, kind });

describe('projection-independent map renderer helpers', () => {
	it('maps percentage and normalized coordinates to imported pixels', () => {
		expect(pointToPixels(point('p', 25), document)).toEqual([250, 100]);
		expect(pointToPixels(point('n', 0.25), document)).toEqual([250, 100]);
		expect(pointToPercent(point('p', 25))).toEqual([25, 20]);
	});

	it('keeps region anchors visible while reducing dense points at low zoom', () => {
		const points = Array.from({ length: 500 }, (_, index) => point(`p-${index}`, index % 100));
		points.push(point('region', 50, 'region'));
		const reduced = visibleWorldPoints(points, 0.7);
		expect(reduced).toContain(points.at(-1));
		expect(reduced.length).toBeLessThan(points.length);
	});

	it('scales marker radius without allowing unreadable sizes', () => {
		expect(pointRadius(point('p', 20), 1)).toBe(6);
		expect(pointRadius(point('p', 20), 0.1)).toBe(9.486832980505138);
		expect(pointRadius(point('p', 20), 10)).toBe(3);
	});
});
