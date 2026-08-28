export type IPAChartCell = [string | null, string | null]; // [voiceless, voiced]

// Řádky (Způsob artikulace) x Sloupce (Místo artikulace)
// B = Bilabial, Ld = Labiodental, D = Dental, A = Alveolar, Pa = Postalveolar,
// R = Retroflex, P = Palatal, V = Velar, U = Uvular, Ph = Pharyngeal, G = Glottal
export const ipaPlaces = [
	'Bilabial', 'Labiodental', 'Dental', 'Alveolar', 'Postalveolar', 
	'Retroflex', 'Palatal', 'Velar', 'Uvular', 'Pharyngeal', 'Glottal'
];

export const ipaManners = [
	'Plosive', 'Nasal', 'Trill', 'Tap/Flap', 'Fricative', 
	'Lateral fricative', 'Approximant', 'Lateral approximant'
];

export const ipaConsonants: Record<string, Record<string, IPAChartCell>> = {
	'Plosive': {
		'Bilabial': ['p', 'b'], 'Alveolar': ['t', 'd'], 'Retroflex': ['ʈ', 'ɖ'], 
		'Palatal': ['c', 'ɟ'], 'Velar': ['k', 'g'], 'Uvular': ['q', 'ɢ'], 'Glottal': ['ʔ', null]
	},
	'Nasal': {
		'Bilabial': [null, 'm'], 'Labiodental': [null, 'ɱ'], 'Alveolar': [null, 'n'], 
		'Retroflex': [null, 'ɳ'], 'Palatal': [null, 'ɲ'], 'Velar': [null, 'ŋ'], 'Uvular': [null, 'ɴ']
	},
	'Trill': {
		'Bilabial': [null, 'ʙ'], 'Alveolar': [null, 'r'], 'Uvular': [null, 'ʀ']
	},
	'Tap/Flap': {
		'Labiodental': [null, 'ⱱ'], 'Alveolar': [null, 'ɾ'], 'Retroflex': [null, 'ɽ']
	},
	'Fricative': {
		'Bilabial': ['ɸ', 'β'], 'Labiodental': ['f', 'v'], 'Dental': ['θ', 'ð'], 
		'Alveolar': ['s', 'z'], 'Postalveolar': ['ʃ', 'ʒ'], 'Retroflex': ['ʂ', 'ʐ'], 
		'Palatal': ['ç', 'ʝ'], 'Velar': ['x', 'ɣ'], 'Uvular': ['χ', 'ʁ'], 
		'Pharyngeal': ['ħ', 'ʕ'], 'Glottal': ['h', 'ɦ']
	},
	'Lateral fricative': {
		'Alveolar': ['ɬ', 'ɮ']
	},
	'Approximant': {
		'Labiodental': [null, 'ʋ'], 'Alveolar': [null, 'ɹ'], 'Retroflex': [null, 'ɻ'], 
		'Palatal': [null, 'j'], 'Velar': [null, 'ɰ']
	},
	'Lateral approximant': {
		'Alveolar': [null, 'l'], 'Retroflex': [null, 'ɭ'], 'Palatal': [null, 'ʎ'], 'Velar': [null, 'ʟ']
	}
};

export const ipaVowelsFrontness = ['Front', 'Central', 'Back'];
export const ipaVowelsOpenness = ['Close', 'Near-close', 'Close-mid', 'Mid', 'Open-mid', 'Near-open', 'Open'];

// Structure: Record<Openness, Record<Frontness, [unrounded, rounded]>>
export const ipaVowels: Record<string, Record<string, IPAChartCell>> = {
	'Close': { 'Front': ['i', 'y'], 'Central': ['ɨ', 'ʉ'], 'Back': ['ɯ', 'u'] },
	'Near-close': { 'Front': ['ɪ', 'ʏ'], 'Central': [null, null], 'Back': [null, 'ʊ'] },
	'Close-mid': { 'Front': ['e', 'ø'], 'Central': ['ɘ', 'ɵ'], 'Back': ['ɤ', 'o'] },
	'Mid': { 'Central': ['ə', null] },
	'Open-mid': { 'Front': ['ɛ', 'œ'], 'Central': ['ɜ', 'ɞ'], 'Back': ['ʌ', 'ɔ'] },
	'Near-open': { 'Front': ['æ', null], 'Central': ['ɐ', null] },
	'Open': { 'Front': ['a', 'ɶ'], 'Central': [null, null], 'Back': ['ɑ', 'ɒ'] }
};

export interface LanguagePreset {
	id: string;
	name: string;
	consonants: string[];
	vowels: string[];
	syllable: string;
}

export const languagePresets: LanguagePreset[] = [
	{
		id: 'empty',
		name: 'Vlastní (Prázdný)',
		consonants: [],
		vowels: [],
		syllable: '(C)V'
	},
	{
		id: 'cs',
		name: 'Čeština',
		consonants: ['p', 'b', 't', 'd', 'c', 'ɟ', 'k', 'g', 'm', 'n', 'ɲ', 'r', 'f', 'v', 's', 'z', 'ʃ', 'ʒ', 'x', 'h', 'j', 'l', 'r̝'], // 'r̝' je striktní IPA pro české 'ř'
		vowels: ['i', 'e', 'a', 'o', 'u', 'ɪ', 'ɛ'],
		syllable: '(C)(C)(C)V(C)(C)(C)'
	},
	{
		id: 'en',
		name: 'Angličtina',
		consonants: ['p', 'b', 't', 'd', 'k', 'g', 'm', 'n', 'ŋ', 'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ', 'h', 'ɹ', 'j', 'l'],
		vowels: ['i', 'ɪ', 'e', 'ɛ', 'æ', 'a', 'ɑ', 'ɒ', 'ɔ', 'ʌ', 'o', 'ʊ', 'u', 'ə'],
		syllable: '(C)(C)(C)V(C)(C)(C)(C)'
	},
	{
		id: 'pie',
		name: 'Proto-Indo-European (Tradiční)',
		consonants: ['p', 'b', 't', 'd', 'k', 'g', 'm', 'n', 'r', 's', 'j', 'l'],
		vowels: ['e', 'o'],
		syllable: '(C)(C)V(C)(C)'
	}
];
