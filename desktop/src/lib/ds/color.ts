// Barvy jazyků. Málo jazyků: každý má vlastní barvu z --l0…--l5 (sousední v čase se nepotkají).
// Mnoho jazyků (víc než 8): odstín nese rodina (protojazyk), světlost jazyk v rodině.

export interface ColorLineage {
	id: string;
	start: number;
	end?: number | null;
	parent?: string | null;
	/** index rodiny (protojazyka) 0–5 */
	family?: number;
}

export type LanguagePalette = Map<string, string>;

/** Hodnota CSS proměnné z kořene dokumentu (pro kreslení do canvasu). */
export function cssVar(name: string): string {
	if (typeof document === 'undefined') return '#888';
	return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}

/** Odstín barvy rodiny: n-tý jazyk v rodině dostane jinou světlost. */
export function shadeOf(hex: string, n: number): string {
	const v = parseInt(hex.replace('#', ''), 16);
	const r = (v >> 16) / 255, g = ((v >> 8) & 255) / 255, b = (v & 255) / 255;
	const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
	const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
	let h = 0;
	if (d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
	const steps = [0, 0.13, -0.11, 0.24, -0.2, 0.06, -0.05, 0.18, -0.15, 0.3];
	const L = Math.max(0.18, Math.min(0.82, l + steps[n % steps.length]));
	return `hsl(${Math.round(h * 60 + 360) % 360} ${Math.round(sat * 100)}% ${Math.round(L * 100)}%)`;
}

/** Přidělí barvy jazykům. Vrací mapu id → barva (konkrétní hodnota, použitelná v canvasu i CSS). */
export function languagePalette(lineages: ColorLineage[]): LanguagePalette {
	const out: LanguagePalette = new Map();
	const order = [...lineages].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id));
	const base = (k: number) => cssVar(`--l${k % 6}`);
	if (lineages.length > 8) {
		const rank: Record<number, number> = {};
		for (const l of order) {
			const f = l.family ?? 0;
			rank[f] = (rank[f] ?? -1) + 1;
			out.set(l.id, shadeOf(base(f), rank[f]));
		}
		return out;
	}
	const used: { start: number; end: number; c: number }[] = [];
	const slot = new Map<string, number>();
	for (const l of order) {
		const end = l.end ?? 1e9;
		const busy = new Set(used.filter((u) => u.start < end && u.end > l.start).map((u) => u.c));
		const parent = l.parent != null ? slot.get(l.parent) : undefined;
		let c = [0, 1, 2, 3, 4, 5].find((k) => !busy.has(k) && k !== parent);
		if (c === undefined) c = used.length % 6;
		slot.set(l.id, c);
		used.push({ start: l.start, end, c });
		out.set(l.id, base(c));
	}
	return out;
}

/** Barva rodiny (protojazyka) podle indexu. */
export const familyColor = (index: number) => cssVar(`--l${index % 6}`);
