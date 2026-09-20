import { describe, expect, it } from 'vitest';
import { endLanguage, focusBranch, migrateLegacyWorldModel, splitLanguage, validateGenealogy, GenealogyValidationError } from './world-model';

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
			tradeRoutes: [{ id: 'route-1', languageIds: ['a', 'b'], startYear: 20, intensity: 0.8, geometry: { kind: 'line', points: [{ x: 10, y: 20 }, { x: 30, y: 40 }] } }],
			polities: [{ id: 'polity-1', name: 'Říční liga', kind: 'confederation', startYear: 10, geometry: { kind: 'polygon', points: [{ x: 1, y: 1 }, { x: 4, y: 1 }, { x: 4, y: 4 }] } }],
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
		expect(model.map.routes[0]).toMatchObject({
			label: 'Trasa 1',
			geometry: { kind: 'line', points: [{ x: 10, y: 20 }, { x: 30, y: 40 }] }
		});
		expect(model.map.politicalEntities[0]).toMatchObject({
			name: 'Říční liga',
			kind: 'confederation',
			geometry: { kind: 'polygon' }
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

describe('genealogical editor actions', () => {
	function model() {
		return migrateLegacyWorldModel({
			timeSteps: [0, 100, 200],
			snapshots: { 0: { nodes: [{ id: 'root', position: { x: 10, y: 20 }, data: { label: 'Root', familyId: 'f' } }] } }
		});
	}

	it('splits a language, records an inherited relation and leaves geography untouched', () => {
		const before = model();
		const next = splitLanguage(before, { parentId: 'root', year: 100, children: [{ id: 'west', name: 'West' }, { id: 'east', name: 'East' }] });
		expect(next.languages.find((language) => language.id === 'root')?.interval.endYear).toBe(100);
		expect(next.languages.find((language) => language.id === 'west')).toMatchObject({ parentLanguageId: 'root', interval: { startYear: 100, endYear: null } });
		expect(next.relations.filter((relation) => relation.kind === 'inherited')).toHaveLength(2);
		expect(next.events.at(-1)).toMatchObject({ kind: 'split', participantIds: ['root', 'west', 'east'] });
		expect(next.presences).toEqual(before.presences);
		expect(next.map).toEqual(before.map);
		expect(focusBranch(next, 'root').sort()).toEqual(['east', 'root', 'west']);
	});

	it('ends a language without removing it or its geographic presence', () => {
		const before = model();
		const next = endLanguage(before, { languageId: 'root', year: 50 });
		expect(next.languages[0]).toMatchObject({ status: 'dead', interval: { startYear: 0, endYear: 50 } });
		expect(next.events.at(-1)).toMatchObject({ kind: 'death', participantIds: ['root'] });
		expect(next.presences).toEqual(before.presences);
	});

	it('rejects cycles, duplicate ids and children born after a dead parent', () => {
		const broken = model();
		broken.languages[0].parentLanguageId = 'root';
		expect(() => validateGenealogy(broken)).toThrow(GenealogyValidationError);
		expect(() => splitLanguage(model(), { parentId: 'root', year: 100, children: [{ id: 'root', name: 'Duplicate' }] })).toThrow(/už existuje/);
		const dead = endLanguage(model(), { languageId: 'root', year: 50 });
		expect(() => splitLanguage(dead, { parentId: 'root', year: 100, children: [{ id: 'late', name: 'Late' }] })).toThrow(/mimo jeho interval/);
	});
});
