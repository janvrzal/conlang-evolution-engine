import { resolveApiBase } from '$lib/api';
import type { LanguageWord } from '$lib/LanguageLexicon.svelte';

export type LexiconFilters = {
	query: string;
	register: string;
	community: string;
	lexicalClass: string;
};

export type LanguagePage = {
	words: LanguageWord[];
	total: number;
	nextOffset: number | null;
	facets: {
		registers: string[];
		communities: string[];
		lexicalClasses: string[];
		homonymForms: string[];
		synonymConcepts: string[];
	};
};

export async function fetchLanguagePage(
	runId: string,
	nodeId: string,
	year: number,
	offset: number,
	filters: LexiconFilters
): Promise<LanguagePage> {
	const base = await resolveApiBase();
	const parameters = new URLSearchParams({ year: String(year), offset: String(offset), limit: '100' });
	if (filters.query) parameters.set('query', filters.query);
	if (filters.register !== 'all') parameters.set('register', filters.register);
	if (filters.community !== 'all') parameters.set('community', filters.community);
	if (filters.lexicalClass !== 'all') parameters.set('lexical_class', filters.lexicalClass);
	const response = await fetch(
		`${base}/api/runs/${encodeURIComponent(runId)}/languages/${encodeURIComponent(nodeId)}/page?${parameters}`
	);
	if (!response.ok) throw new Error(`Načtení slovníku selhalo: ${response.status}`);
	const body = await response.json();
	return {
		words: body.words,
		total: body.total,
		nextOffset: body.next_offset,
		facets: {
			registers: body.facets?.registers ?? [],
			communities: body.facets?.communities ?? [],
			lexicalClasses: body.facets?.lexical_classes ?? [],
			homonymForms: body.facets?.homonym_forms ?? [],
			synonymConcepts: body.facets?.synonym_concepts ?? []
		}
	};
}
