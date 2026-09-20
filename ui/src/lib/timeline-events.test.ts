import { describe, expect, it } from 'vitest';
import {
	draftToHistoricalEvent,
	historicalEventToLegacy,
	newHistoricalEventDraft,
	validateHistoricalEvent
} from './timeline-events';

const languages = new Set(['a', 'b']);

describe('historical event timeline contract', () => {
	it('requires two participants for contact and war', () => {
		const draft = { ...newHistoricalEventDraft(100), kind: 'contact' as const, title: 'Setkání', participantIds: ['a'] };
		expect(validateHistoricalEvent(draft, languages)).toEqual({ valid: false, errors: ['Kontakt vyžaduje alespoň 2 účastníky.'] });
	});

	it('rejects inverted intervals and unknown languages', () => {
		const draft = { ...newHistoricalEventDraft(100), title: 'Válka', endYear: 50, kind: 'war' as const, participantIds: ['a', 'missing'] };
		const result = validateHistoricalEvent(draft, languages);
		expect(result.valid).toBe(false);
		if (!result.valid) expect(result.errors).toEqual(expect.arrayContaining(['Konec nesmí předcházet začátku.', 'Neznámý jazyk: missing.']));
	});

	it('round-trips interval events to the legacy shape without geometry or edges', () => {
		const event = draftToHistoricalEvent({ ...newHistoricalEventDraft(-20), kind: 'migration', title: 'Příchod', endYear: 10, participantIds: ['a'] }, 'event-1');
		expect(event).toMatchObject({ id: 'event-1', interval: { startYear: -20, endYear: 10 }, participantIds: ['a'] });
		expect(historicalEventToLegacy(event)).toMatchObject({ id: 'event-1', startYear: -20, duration: 30, targetLanguageIds: ['a'] });
		expect(event).not.toHaveProperty('geometry');
		expect(event).not.toHaveProperty('source');
	});
});
