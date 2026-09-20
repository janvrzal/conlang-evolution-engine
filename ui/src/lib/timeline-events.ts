import type { EntityId, HistoricalEvent, HistoricalEventKind, LanguageEntity, YearInterval } from '$lib/world-model';

/**
 * Contract for the historical-event editor.
 *
 * Events are interval entities. They may reference languages (and, in the
 * future, polities/regions through effects), but they never contain geometry
 * or genealogical edges. The map and genealogy screens consume the event; they
 * do not get mutated as a side effect of editing it.
 */
export const HISTORICAL_EVENT_KINDS: readonly HistoricalEventKind[] = [
	'migration',
	'contact',
	'war',
	'standardization',
	'split',
	'renaming',
	'death',
	'other'
] as const;

export const HISTORICAL_EVENT_LABELS: Record<HistoricalEventKind, string> = {
	migration: 'Migrace',
	contact: 'Kontakt',
	war: 'Válka',
	standardization: 'Standardizace',
	split: 'Štěpení',
	renaming: 'Přejmenování',
	death: 'Zánik',
	other: 'Jiná událost'
};

export type HistoricalEventDraft = {
	id?: string;
	kind: HistoricalEventKind;
	startYear: number;
	endYear: number | null;
	participantIds: string[];
	title: string;
	effects: Record<string, unknown>;
	metadata: Record<string, unknown>;
};

export type EventValidation = { valid: true } | { valid: false; errors: string[] };

export const newHistoricalEventDraft = (year = 0): HistoricalEventDraft => ({
	kind: 'migration',
	startYear: year,
	endYear: null,
	participantIds: [],
	title: '',
	effects: {},
	metadata: {}
});

export function eventToDraft(event: HistoricalEvent): HistoricalEventDraft {
	return {
		id: event.id,
		kind: event.kind,
		startYear: event.interval.startYear,
		endYear: event.interval.endYear,
		participantIds: [...event.participantIds],
		title: event.title,
		effects: { ...event.effects },
		metadata: { ...event.metadata }
	};
}

export function validateHistoricalEvent(
	draft: HistoricalEventDraft,
	knownLanguageIds?: ReadonlySet<string>
): EventValidation {
	const errors: string[] = [];
	if (!HISTORICAL_EVENT_KINDS.includes(draft.kind)) errors.push('Neplatný typ události.');
	if (!Number.isInteger(draft.startYear)) errors.push('Začátek musí být celé číslo.');
	if (draft.endYear !== null && !Number.isInteger(draft.endYear)) errors.push('Konec musí být celé číslo.');
	if (draft.endYear !== null && draft.endYear < draft.startYear) errors.push('Konec nesmí předcházet začátku.');
	if (!draft.title.trim()) errors.push('Událost musí mít název.');
	const uniqueParticipants = new Set(draft.participantIds.filter(Boolean));
	if (uniqueParticipants.size !== draft.participantIds.length) errors.push('Účastníci nesmí být duplicitní.');
	if (knownLanguageIds) {
		for (const id of uniqueParticipants) if (!knownLanguageIds.has(id)) errors.push(`Neznámý jazyk: ${id}.`);
	}
	const minimum = draft.kind === 'war' || draft.kind === 'contact' ? 2 : 1;
	if (uniqueParticipants.size < minimum) {
		errors.push(`${HISTORICAL_EVENT_LABELS[draft.kind]} vyžaduje alespoň ${minimum === 2 ? '2 účastníky' : '1 účastníka'}.`);
	}
	return errors.length ? { valid: false, errors } : { valid: true };
}

export function draftToHistoricalEvent(draft: HistoricalEventDraft, id: EntityId): HistoricalEvent {
	return {
		id,
		kind: draft.kind,
		interval: { startYear: draft.startYear, endYear: draft.endYear } satisfies YearInterval,
		participantIds: [...new Set(draft.participantIds.filter(Boolean))],
		title: draft.title.trim(),
		effects: { ...draft.effects },
		metadata: { ...draft.metadata }
	};
}

export function sortHistoricalEvents(events: readonly HistoricalEvent[]): HistoricalEvent[] {
	return [...events].sort((a, b) => a.interval.startYear - b.interval.startYear || a.title.localeCompare(b.title));
}

export function eventParticipants(event: HistoricalEvent, languages: readonly LanguageEntity[]): string {
	const names = new Map(languages.map((language) => [language.id, language.name]));
	return event.participantIds.map((id) => names.get(id) ?? id).join(', ');
}

/** The legacy backend shape is retained as a projection only. */
export function historicalEventToLegacy(event: HistoricalEvent): Record<string, unknown> {
	const duration = event.interval.endYear === null ? 0 : Math.max(0, event.interval.endYear - event.interval.startYear);
	return {
		id: event.id,
		kind: event.kind,
		startYear: event.interval.startYear,
		duration,
		targetLanguageIds: [...event.participantIds],
		effects: { ...event.effects },
		title: event.title
	};
}
