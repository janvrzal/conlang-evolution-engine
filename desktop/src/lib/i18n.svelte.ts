// Popisky aplikace česky a anglicky. Každý text UI jde přes t(); katalogy
// jsou v messages/ a anglický musí mít stejné klíče jako český (hlídá typ).
import cs from './messages/cs';
import en from './messages/en';

export { plural } from './plural';

export type Locale = 'cs' | 'en';
export type MessageKey = keyof typeof cs;
type Params = Record<string, string | number>;
export type Message = string | ((params: Params) => string);

const catalogs: Record<Locale, Record<MessageKey, Message>> = { cs, en };
const STORAGE_KEY = 'cee-locale';

function initial(): Locale {
	try {
		const saved = localStorage.getItem(STORAGE_KEY);
		if (saved === 'cs' || saved === 'en') return saved;
	} catch {
		// Úložiště nemusí být k dispozici; pak rozhodne jazyk systému.
	}
	return typeof navigator !== 'undefined' && navigator.language.startsWith('cs') ? 'cs' : 'en';
}

let current = $state<Locale>(typeof window === 'undefined' ? 'cs' : initial());

export const i18n = {
	get locale(): Locale {
		return current;
	},
	set locale(value: Locale) {
		current = value;
		try {
			localStorage.setItem(STORAGE_KEY, value);
		} catch {
			// Volba jazyka pak platí jen do zavření okna.
		}
		if (typeof document !== 'undefined') document.documentElement.lang = value;
	}
};

/** Text pro klíč v aktuálním jazyce; parametry se dosadí do {jmen}. */
export function t(key: MessageKey, params: Params = {}): string {
	const message = catalogs[current][key] ?? catalogs.cs[key];
	if (typeof message === 'function') return message(params);
	return message.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));
}

/** Číslo s oddělovači tisíců podle jazyka. */
export function number(n: number): string {
	return n.toLocaleString(current === 'cs' ? 'cs-CZ' : 'en-GB');
}
