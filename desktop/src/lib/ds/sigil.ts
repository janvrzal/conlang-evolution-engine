// Značka jazyka (varianta C+, „rodokmen jména“): vlastní jméno jazyka (IPA) vyroste jako malá značka CEE.
// Slabika = dělení kmene křivkou S, souhlásky ohnou kmen (retné a přední nahoru, zadní dolů),
// samohláska vyžene výhonek (přední nahoru, zadní dolů, nízká delší). Příbuzné jazyky mají podobná
// jména, a tak i podobné značky. Výsledek je jeden vyplněný tvar s proměnnou tloušťkou.

type Pt = [number, number];
interface Feat {
	v: boolean;
	/** samohláska: 0 přední, 1 střední, 2 zadní */
	back: number;
	/** samohláska: 0 nízká … 2 vysoká */
	h: number;
	/** souhláska: 0 retná, 1 přední (zubní, dásňová), 2 palatální a postalveolární, 3 zadní */
	place: number;
	/** souhláska: s ražená, f třená, n nosová, a aproximanta, c polozávěrová */
	man: 's' | 'f' | 'n' | 'a' | 'c';
}

const V: Record<string, [number, number]> = {
	i: [0, 2], y: [0, 2], ɪ: [0, 1.6], ʏ: [0, 1.6], e: [0, 1], ø: [0, 1], ɛ: [0, 0.6], œ: [0, 0.6], æ: [0, 0], a: [1, 0], ɶ: [0, 0],
	ɨ: [1, 2], ʉ: [1, 2], ə: [1, 1], ɘ: [1, 1], ɵ: [1, 1], ɜ: [1, 0.6], ɐ: [1, 0.3],
	ɯ: [2, 2], u: [2, 2], ʊ: [2, 1.6], ɤ: [2, 1], o: [2, 1], ʌ: [2, 0.6], ɔ: [2, 0.6], ɑ: [2, 0], ɒ: [2, 0]
};
const C: Record<string, [number, Feat['man']]> = {
	p: [0, 's'], b: [0, 's'], m: [0, 'n'], ɸ: [0, 'f'], β: [0, 'f'], f: [0, 'f'], v: [0, 'f'], w: [0, 'a'], ʋ: [0, 'a'], ɱ: [0, 'n'],
	t: [1, 's'], d: [1, 's'], n: [1, 'n'], θ: [1, 'f'], ð: [1, 'f'], s: [1, 'f'], z: [1, 'f'], l: [1, 'a'], r: [1, 'a'], ɾ: [1, 'a'], ɹ: [1, 'a'], ɬ: [1, 'f'],
	ʃ: [2, 'f'], ʒ: [2, 'f'], ɕ: [2, 'f'], ʑ: [2, 'f'], ç: [2, 'f'], ʝ: [2, 'f'], j: [2, 'a'], ʎ: [2, 'a'], ɲ: [2, 'n'], c: [2, 's'], ɟ: [2, 's'], ʂ: [2, 'f'], ʐ: [2, 'f'], ɳ: [2, 'n'],
	k: [3, 's'], g: [3, 's'], ɡ: [3, 's'], ŋ: [3, 'n'], x: [3, 'f'], ɣ: [3, 'f'], q: [3, 's'], χ: [3, 'f'], ʁ: [3, 'f'], ʀ: [3, 'a'], h: [3, 'f'], ɦ: [3, 'f'], ʔ: [3, 's'], ħ: [3, 'f'], ʕ: [3, 'f'], ɰ: [3, 'a']
};
const COMB = /[̀-ͯʰ-˿]/;

/** rozdělí IPA na hlásky: diakritika, ʲ a tóny patří k předchozí hlásce, t͡ʃ je jedna hláska */
export function segments(ipa: string): string[] {
	const a = [...ipa.normalize('NFD')], o: string[] = [];
	for (let i = 0; i < a.length; i++) {
		const c = a[i];
		if (c === '͡' || c === '͜') {
			if (o.length) o[o.length - 1] += c + (a[i + 1] ?? '');
			i++;
			continue;
		}
		if (COMB.test(c) || c === 'ː') {
			if (o.length) o[o.length - 1] += c;
			continue;
		}
		if (/[\s.ˈˌ/[\]*-]/.test(c)) continue;
		o.push(c);
	}
	return o;
}
function feat(t: string): Feat {
	const b = t[0];
	if (V[b]) return { v: true, back: V[b][0], h: V[b][1], place: 0, man: 'a' };
	const c = C[b] ?? [1, 'a'];
	return { v: false, back: 1, h: 1, place: c[0], man: t.includes('͡') || t.includes('͜') ? 'c' : c[1] };
}

const P = (n: number) => n.toFixed(2);
function cub(a: Pt, b: Pt, c: Pt, d: Pt, t: number): Pt {
	const u = 1 - t;
	return [u * u * u * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t * t * t * d[0], u * u * u * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t * t * t * d[1]];
}
function stroke(a: Pt, b: Pt, c: Pt, d: Pt, w0: number, w1: number, box: Pt[]) {
	const N = 20, L: Pt[] = [], R: Pt[] = [];
	for (let i = 0; i <= N; i++) {
		const t = i / N, p = cub(a, b, c, d, t), q = cub(a, b, c, d, Math.min(1, t + 0.01)), r = cub(a, b, c, d, Math.max(0, t - 0.01));
		let dx = q[0] - r[0], dy = q[1] - r[1];
		const n = Math.hypot(dx, dy) || 1;
		dx /= n;
		dy /= n;
		const w = (w0 + (w1 - w0) * t) / 2;
		L.push([p[0] - dy * w, p[1] + dx * w]);
		R.push([p[0] + dy * w, p[1] - dx * w]);
		box.push(L[L.length - 1], R[R.length - 1]);
	}
	return 'M' + L.concat(R.reverse()).map((q) => P(q[0]) + ' ' + P(q[1])).join('L') + 'Z';
}
const line = (a: Pt, b: Pt, w0: number, w1: number, box: Pt[]) => stroke(a, [a[0] + (b[0] - a[0]) / 3, a[1]], [a[0] + (2 * (b[0] - a[0])) / 3, b[1]], b, w0, w1, box);
const sline = (a: Pt, b: Pt, w0: number, w1: number, box: Pt[]) => stroke(a, [(a[0] + b[0]) / 2, a[1]], [(a[0] + b[0]) / 2, b[1]], b, w0, w1, box);

export interface Sigil {
	d: string;
	/** čtvercový záběr kolem tvaru */
	view: [number, number, number];
}

/** Značka jazyka z jeho vlastního jména v IPA. */
export function sigil(ipa: string): Sigil {
	const T = segments(ipa);
	const syl: string[][] = [];
	let cur: string[] = [];
	for (const t of T) {
		cur.push(t);
		if (feat(t).v) {
			syl.push(cur);
			cur = [];
		}
	}
	if (cur.length) {
		if (syl.length) syl[syl.length - 1].push(...cur);
		else syl.push(cur);
	}
	const box: Pt[] = [];
	let x = 0, y = 0, w = 4.6, d = line([-3, 0], [0, 0], 4.6, 4.6, box);
	for (const s of syl) {
		let dy = 0;
		for (const t of s) {
			const f = feat(t);
			if (!f.v) dy += [-5, -2, 2, 5][f.place] * (f.man === 'a' ? 0.5 : 1);
		}
		dy = Math.max(-9, Math.min(9, dy));
		const v = s.map(feat).find((f) => f.v) ?? { back: 1, h: 1 };
		const nw = w * 0.84, nx = x + 9, ny = y + dy;
		d += sline([x, y], [nx, ny], w, nw, box);
		const sl = 5 + (2 - v.h) * 3.5, sd = v.back === 0 ? -1 : v.back === 2 ? 1 : dy > 0 ? -1 : 1;
		d += sline([nx, ny], [nx + sl * 0.8, ny + sd * sl], nw * 0.85, nw * 0.4, box);
		x = nx;
		y = ny;
		w = nw;
	}
	d += line([x, y], [x + 5, y], w, w * 0.6, box);
	let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
	for (const [px, py] of box) {
		x0 = Math.min(x0, px);
		y0 = Math.min(y0, py);
		x1 = Math.max(x1, px);
		y1 = Math.max(y1, py);
	}
	const s = Math.max(x1 - x0, y1 - y0) + 4;
	return { d, view: [(x0 + x1) / 2 - s / 2, (y0 + y1) / 2 - s / 2, s] };
}
