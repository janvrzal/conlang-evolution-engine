// Jména krajů, jazyků a nářečí z jazyka světa, česky i anglicky.
//
// Engine dodá fakta (cee.v2.naming): vlastní jméno jazyka v IPA, kraj vzniku
// a polohu nářečí. Tady se z nich skládá jméno v jazyce rozhraní. Přepis IPA
// do latinky je zatím jeden pro oba jazyky; vlastní pravopis světa přijde později.
import type { Locale } from './i18n.svelte';

const MOD = /[̀-ͯʰ-˿]/;
const VOWEL = /^[aeiouyæøɛɔəɪʊɨʉɯɤʌœɞɶɑɒɘɵʏ]/;

export function segments(ipa: string): string[] {
	const out: string[] = [];
	for (const ch of ipa) {
		if (out.length && (MOD.test(ch) || out[out.length - 1].endsWith('͡'))) out[out.length - 1] += ch;
		else out.push(ch);
	}
	return out;
}

const ROMAN: Record<string, string> = {
	kʷ: 'kw', ɡʷ: 'gw', ɡ: 'g', ʃ: 'š', ʒ: 'ž', 't͡ʃ': 'č', 'd͡ʒ': 'dž', 't͡s': 'c', 'd͡z': 'dz', ŋ: 'ng', ɲ: 'ň',
	θ: 'th', ð: 'dh', x: 'ch', ɣ: 'gh', ʔ: '’', ə: 'e', ɛ: 'e', æ: 'ä', ø: 'ö', ɔ: 'o', ʊ: 'u', ɪ: 'i', y: 'ü',
	ɨ: 'y', β: 'v', ɸ: 'f', χ: 'ch', ʁ: 'r', ħ: 'h', ɦ: 'h', ʎ: 'ľ', ɬ: 'hl', c: 'ť', ɟ: 'ď', ɢ: 'g', ʋ: 'v',
	ɹ: 'r', ɰ: 'g', ʝ: 'j', ɑ: 'a', ɒ: 'o', ʌ: 'a'
};

/** Přepis IPA do latinky s velkým počátečním písmenem. */
export function romanize(ipa: string): string {
	const text = segments(ipa).map((s) => ROMAN[s] ?? s).join('');
	return text.charAt(0).toUpperCase() + text.slice(1);
}

const stem = (name: string) => {
	const lower = name.toLowerCase().replace(/’/g, '');
	return lower.length > 3 ? lower.replace(/[aeiouyäöü]+$/, '') || lower : lower;
};

/** České přídavné jméno kraje: Su → suský / suská / suské. */
export function regionAdjective(name: string, gender: 'm' | 'f' | 'n' = 'f'): string {
	const end = { m: 'ý', f: 'á', n: 'é' }[gender];
	const base = stem(name);
	if (/[kc]$/.test(base)) return `${base.slice(0, -1)}ck${end}`;
	if (/s$/.test(base)) return `${base}k${end}`;
	return `${base}sk${end}`;
}

/** Jméno jazyka z jeho vlastního jména: Libodi → libodština / Libodi. */
export function languageFromEndonym(endonym: string, locale: Locale): string {
	return locale === 'cs' ? `${stem(endonym)}ština` : endonym;
}

export interface LanguageFacts {
	id: string;
	parent: string | null;
	/** Vlastní jméno (IPA) z exportu; u vymřelého jazyka poslední známé. */
	endonym: string | null;
	/** Jméno kraje, kde jazyk vznikl. */
	origin: string | null;
}

/**
 * Jména jazyků v pořadí vzniku. Protojazyk a dceřiný jazyk, jehož vlastní jméno
 * se už liší od ostatních, se jmenují podle vlastního jména; jinak dceřiný jazyk
 * dostane jméno podle kraje vzniku („suská tedština“, „Su Tedi“).
 */
export function languageNames(languages: LanguageFacts[], locale: Locale): Map<string, string> {
	const names = new Map<string, string>();
	const taken = new Set<string>();
	for (const language of languages) {
		const endonym = language.endonym ? romanize(language.endonym) : language.id;
		let name = languageFromEndonym(endonym, locale);
		const parent = language.parent ? names.get(language.parent) : null;
		if (taken.has(name) && language.origin) {
			const base = parent ?? name;
			name = locale === 'cs' ? `${regionAdjective(language.origin, 'f')} ${base}` : `${language.origin} ${base}`;
		}
		let unique = name;
		for (let n = 2; taken.has(unique); n++) unique = `${name} ${n}`;
		taken.add(unique);
		names.set(language.id, unique);
	}
	return names;
}

export interface DialectFacts {
	regions: string[];
	direction: string;
	terrain: string | null;
	sole: boolean;
	/** Směr uvnitř hlavního kraje; rozliší dvě nářečí téhož kraje. */
	local?: string;
}

const DIRECTION: Record<Locale, Record<string, string>> = {
	cs: { center: 'střední', north: 'severní', south: 'jižní', east: 'východní', west: 'západní',
		northeast: 'severovýchodní', northwest: 'severozápadní', southeast: 'jihovýchodní', southwest: 'jihozápadní' },
	en: { center: 'Central', north: 'Northern', south: 'Southern', east: 'Eastern', west: 'Western',
		northeast: 'North-eastern', northwest: 'North-western', southeast: 'South-eastern', southwest: 'South-western' }
};
const TERRAIN: Record<Locale, Record<string, string>> = {
	cs: { mountains: 'horské', island: 'ostrovní', hills: 'podhorské' },
	en: { mountains: 'Highland', island: 'Island', hills: 'Upland' }
};

/**
 * Jména nářečí jednoho jazyka, od nejobecnějšího k přesnějšímu, dokud se liší:
 * krajina nebo směr od středu jazyka → hlavní kraj → směr v kraji a kraj.
 */
export function dialectNames(dialects: DialectFacts[], regionName: (id: string) => string, locale: Locale): string[] {
	const levels = dialects.map((d) => {
		const region = d.regions.length ? regionName(d.regions[0]) : null;
		const regional = region === null ? null : locale === 'cs' ? regionAdjective(region, 'n') : region;
		const first = TERRAIN[locale][d.terrain ?? ''] ?? DIRECTION[locale][d.direction] ?? DIRECTION[locale].center;
		const local = DIRECTION[locale][d.local ?? 'center'];
		return [first, regional, regional && `${local} ${locale === 'cs' ? regional : region}`].filter(
			(x): x is string => Boolean(x)
		);
	});
	const pick = dialects.map(() => 0);
	for (let round = 0; round < 3; round++) {
		const count = new Map<string, number>();
		levels.forEach((l, i) => count.set(l[pick[i]], (count.get(l[pick[i]]) ?? 0) + 1));
		levels.forEach((l, i) => {
			if ((count.get(l[pick[i]]) ?? 0) > 1 && pick[i] + 1 < l.length) pick[i] += 1;
		});
	}
	const used = new Map<string, number>();
	return dialects.map((d, i) => {
		if (d.sole) return locale === 'cs' ? 'jednotná řeč' : 'single variety';
		const label = levels[i][pick[i]];
		const n = (used.get(label) ?? 0) + 1;
		used.set(label, n);
		const numbered = n > 1 ? `${label} ${n}` : label;
		return locale === 'cs' ? `${numbered} nářečí` : `${numbered} dialect`;
	});
}
