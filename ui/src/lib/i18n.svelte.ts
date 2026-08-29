import { browser } from '$app/environment';

export type Locale = 'cs' | 'en';

const messages = {
	cs: {
		interaction: 'Interakce', relationship: 'Vztah', inheritance: 'Dědičnost', contact: 'Kontakt',
		moveHint: 'Výběr, posun a úprava uzlů', relationshipHint: 'Vytvořit vztah mezi jazyky',
		projectSettings: 'Upravit projekt a protojazyk', addNode: 'Přidat uzel', simulate: 'Spustit vývoj',
		project: 'Projekt', year: 'Rok', language: 'Jazyk', importLegacy: 'Načíst dřívější simulaci',
		backToMap: 'Na mapu', backToMenu: 'Zpět do menu', nodeDetail: 'Detail uzlu',
		languageName: 'Název jazyka', bornYear: 'Vznik v roce', deadLanguage: 'Jazyk je mrtvý',
		currentStep: 'Aktuální krok', saved: 'Uloženo', loading: 'Načítám…',
		lexiconUnavailable: 'Spusť simulaci; pak zde uvidíš slovník v aktuálním roce.',
		searchWord: 'Hledat slovo, význam…', lexicon: 'Slovník', stateInYear: 'stav v roce'
	},
	en: {
		interaction: 'Interact', relationship: 'Relationship', inheritance: 'Inheritance', contact: 'Contact',
		moveHint: 'Select, move, and edit nodes', relationshipHint: 'Create a relationship between languages',
		projectSettings: 'Edit project and proto-language', addNode: 'Add node', simulate: 'Run evolution',
		project: 'Project', year: 'Year', language: 'Language', importLegacy: 'Import previous simulation',
		backToMap: 'To map', backToMenu: 'Back to menu', nodeDetail: 'Node details',
		languageName: 'Language name', bornYear: 'Born in year', deadLanguage: 'Language is extinct',
		currentStep: 'Current step', saved: 'Saved', loading: 'Loading…',
		lexiconUnavailable: 'Run the simulation to see this language at the current year.',
		searchWord: 'Search word or meaning…', lexicon: 'Lexicon', stateInYear: 'state in year'
	}
} as const;

export const i18n = $state({ locale: 'cs' as Locale });

export function t(key: keyof typeof messages.cs): string {
	return messages[i18n.locale][key];
}

export function setLocale(locale: Locale): void {
	i18n.locale = locale;
	if (browser) localStorage.setItem('cee-locale', locale);
}

export function restoreLocale(): void {
	if (!browser) return;
	const stored = localStorage.getItem('cee-locale');
	if (stored === 'cs' || stored === 'en') i18n.locale = stored;
}
