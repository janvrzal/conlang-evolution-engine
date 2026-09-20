import { describe, expect, it } from 'vitest';
import { migrateLegacyWorldModel } from './world-model';

describe('migrateLegacyWorldModel', () => {
	it('separates languages, presences and relations from snapshots', () => {
		const model = migrateLegacyWorldModel({
			timeSteps: [0, 100, 200],
			snapshots: {
				0: {
					nodes: [
						{ id: 'proto', position: { x: 3, y: 4 }, data: { label: 'Proto', year: 0 } },
						{ id: 'child', data: { label: 'Child', year: 0 } }
					],
					edges: [{ id: 'split', source: 'proto', target: 'child', data: { year: 0 } }]
				}
				,100: {
					nodes: [
						{ id: 'proto', position: { x: 5, y: 6 }, data: { label: 'Proto', year: 0 } },
						{ id: 'child', data: { label: 'Child', year: 0, isDead: true } }
					],
					edges: [{ id: 'split', source: 'proto', target: 'child', data: { year: 0 } }]
				}
			}
		});

		expect(model.schemaVersion).toBe(1);
		expect(model.map.layers).toMatchObject({ languages: true, routes: false });
		expect(model.map.document).toMatchObject({ width: 2400, height: 1400 });
		expect(model.languages.map((language) => language.id)).toEqual(['child', 'proto']);
		expect(model.languages.find((language) => language.id === 'child')).toMatchObject({
		name: 'Child',
		status: 'dead',
		interval: { startYear: 0, endYear: 100 }
		});
		expect(model.presences.find((presence) => presence.languageId === 'proto')?.geometry).toEqual({
		kind: 'point',
		x: 3,
		y: 4
	});

		expect(model.relations[0]).toMatchObject({
		id: 'split',
		kind: 'inherited',
		sourceId: 'proto',
		targetId: 'child',
		interval: { startYear: 0, endYear: null }
	});
	});

	it('converts routes and historical events without mutating input', () => {
		const input = {
			timeSteps: [0, 100],
			snapshots: { 0: { nodes: [{ id: 'a', data: { label: 'A' } }, { id: 'b', data: { label: 'B' } }] } },
			tradeRoutes: [{ id: 'route-1', languageIds: ['a', 'b'], startYear: 20, intensity: 0.8 }],
			historicalEvents: [
				{ id: 'event-1', kind: 'migration', startYear: 40, duration: 10, targetLanguageIds: ['a'] }
			]
		};
		const before = JSON.stringify(input);
		const model = migrateLegacyWorldModel(input);

		expect(JSON.stringify(input)).toBe(before);
		expect(model.relations).toContainEqual(
			expect.objectContaining({ kind: 'trade', sourceId: 'a', targetId: 'b', interval: { startYear: 20, endYear: null } })
		);
		expect(model.events[0]).toMatchObject({
			id: 'event-1',
			kind: 'migration',
			interval: { startYear: 40, endYear: 50 },
			participantIds: ['a']
		});
	});

	it('keeps geographic defaults separate from genealogy', () => {
		const model = migrateLegacyWorldModel({ timeSteps: [0], snapshots: { 0: { nodes: [{ id: 'a' }] } } });
		model.map.layers.languages = false;
		model.map.points[0].x = 99;
		expect(model.languages).toHaveLength(1);
		expect(model.relations).toHaveLength(0);
	});

	it('is deterministic when imported records have no ids', () => {
		const input = {
			timeSteps: [0],
			snapshots: { 0: { nodes: [{ id: 'a', data: {} }] } },
			historicalEvents: [{ kind: 'war', startYear: 0 }]
		};
		expect(migrateLegacyWorldModel(input)).toEqual(migrateLegacyWorldModel(input));
	});
});
