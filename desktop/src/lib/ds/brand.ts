// Značka CEE v aplikaci: měkký rodokmen ve tvaru E (docs/brand/README.md).
// Stejná geometrie jako docs/brand/nastroje/tree-core.js a states-core.js: každý snímek je JEDEN
// vyplněný <path> (bez švů, bez průhlednosti), přepočítaný z křivek S s plynule se měnící tloušťkou.

interface Branch {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
	w0: number;
	w1: number;
	/** násobič tloušťky konce (vymřelá větev se zúží) */
	k: number;
	d?: number;
	ext?: boolean;
	start?: number;
	dur?: number;
	end?: number;
}
type View = [number, number, number];

const B = (x0: number, y0: number, x1: number, y1: number, w0: number, w1: number): Branch => ({ x0, y0, x1, y1, w0, w1, k: 1 });
const seed = (): Branch[] => [
	B(1.5, 14, 5, 14, 4.4, 4.2),
	B(5, 14, 12, 6.5, 4.2, 3.8),
	B(12, 6.5, 23, 6.5, 3.8, 3.0),
	B(5, 14, 12, 21.25, 4.2, 3.8),
	B(12, 21.25, 18, 16, 3.8, 3.4),
	B(18, 16, 20.5, 16, 3.4, 3.0),
	B(12, 21.25, 18, 26.5, 3.8, 3.4),
	B(18, 26.5, 26, 26.5, 3.4, 2.8)
];
const TIPS: [number, number, number][] = [
	[23, 6.5, 3.0],
	[20.5, 16, 3.0],
	[26, 26.5, 2.8]
];
/** záběr samotné značky (s optickým posunem −0,6) */
export const MARK_VIEW: View = [13.75 - 0.6 - 14.5, 16.3 - 14.5, 29];

const cl = (t: number) => Math.max(0, Math.min(1, t));
const eo = (t: number) => 1 - Math.pow(1 - t, 3);
const io = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

function bez(s: Branch, t: number) {
	const m = (s.x0 + s.x1) / 2, u = 1 - t;
	return [
		u * u * u * s.x0 + 3 * u * u * t * m + 3 * u * t * t * m + t * t * t * s.x1,
		u * u * u * s.y0 + 3 * u * u * t * s.y0 + 3 * u * t * t * s.y1 + t * t * t * s.y1,
		3 * u * u * (m - s.x0) + 3 * t * t * (s.x1 - m),
		6 * u * t * (s.y1 - s.y0)
	];
}
function outline(s: Branch, p = 1, mf?: (x: number) => number) {
	const N = s.y0 === s.y1 ? 2 : 32, L: [number, number][] = [], R: [number, number][] = [];
	for (let i = 0; i <= N; i++) {
		const t = (p * i) / N;
		const [x, y, dx0, dy0] = bez(s, t);
		const n = Math.hypot(dx0, dy0) || 1, dx = dx0 / n, dy = dy0 / n;
		const w = ((s.w0 + (s.w1 * s.k - s.w0) * t) * (mf ? mf(x) : 1)) / 2;
		L.push([x - dy * w, y + dx * w]);
		R.push([x + dy * w, y - dx * w]);
	}
	return 'M' + L.concat(R.reverse()).map((q) => q[0].toFixed(3) + ' ' + q[1].toFixed(3)).join('L') + 'Z';
}
function rng(s: number) {
	return () => {
		s = (s + 0x6d2b79f5) | 0;
		let t = Math.imul(s ^ (s >>> 15), 1 | s);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}
/** potomci značky: rodokmen, který z ramen E vyroste (deterministicky podle semínka) */
function build(sd: number): Branch[] {
	const R = rng(sd), N: Branch[] = [];
	const tips = TIPS.map(([x, y, w]) => ({ ...B(0, 0, x, y, w, w), end: 0.8, d: 0 }));
	function grow(par: Branch, a: number, c: number, md: number) {
		const d = (par.d ?? 0) + 1;
		if (d > md) return;
		const k = c - a < 10 ? 1 : c - a < 20 ? 2 : R() < 0.55 ? 2 : 3, part = (c - a) / k;
		for (let i = 0; i < k; i++) {
			const ext = d > 1 && R() < 0.24, len = [0, 13, 11, 9][d] * (0.7 + R() * 0.6) * (ext ? 0.5 : 1);
			const n = B(par.x1, par.y1, par.x1 + len, a + part * (i + 0.5) + (R() - 0.5) * part * 0.35, par.w1, par.w1 * 0.7);
			n.d = d;
			n.ext = ext;
			n.start = (par.end ?? 0) + 0.05 + R() * 0.35;
			n.dur = 0.45 + R() * 0.5;
			n.end = n.start + n.dur;
			N.push(n);
			if (!ext) grow(n, a + part * i, a + part * (i + 1), md);
		}
	}
	const ys = tips.map((t) => t.y1);
	tips.forEach((tp, i) => {
		const a = i ? (ys[i - 1] + tp.y1) / 2 : tp.y1 - 34, c = i < 2 ? (tp.y1 + ys[i + 1]) / 2 : tp.y1 + 34;
		grow(tp, a, c, c - a > 30 ? 3 : 2);
	});
	return N;
}
function box(N: Branch[]): View {
	let x0 = 1.5, y0 = 4.4, x1 = 26, y1 = 28.2;
	for (const n of N) {
		x0 = Math.min(x0, n.x1);
		x1 = Math.max(x1, n.x1 + 2);
		y0 = Math.min(y0, n.y1 - 2);
		y1 = Math.max(y1, n.y1 + 2);
	}
	const s = Math.max(x1 - x0, y1 - y0) + 10;
	return [(x0 + x1) / 2 - 0.6 - s / 2, (y0 + y1) / 2 - s / 2, s];
}

export interface Frame {
	d: string;
	view: View;
	/** 0–1: jak moc je vidět průvodní text stavu */
	text: number;
}

/** klidná značka */
export const mark = (): Frame => ({ d: seed().map((s) => outline(s)).join(''), view: MARK_VIEW, text: 1 });

/** Prázdný projekt: značka se nadechuje a konce ramen se pomalu natahují (smyčka 4 s). */
export function idle(t: number): Frame {
	const S = seed(), b = Math.sin((2 * Math.PI * t) / 4);
	for (const [i, ph] of [
		[2, 0],
		[5, 1.3],
		[7, 2.6]
	])
		S[i].x1 += 0.7 * Math.sin((2 * Math.PI * (t + ph)) / 4);
	const sc = 1 + 0.03 * b, v = MARK_VIEW[2] / sc;
	return { d: S.map((s) => outline(s)).join(''), view: [13.75 - 0.6 - v / 2, 16.3 - v / 2, v], text: 1 };
}

/** Dosimulováno: hotový rodokmen, kterým od kořene k listům projde vlna (~1,4 s). */
export function done(t: number, sd = 23): Frame {
	const N = build(sd);
	for (const n of N) if (n.ext) n.k = 0.25;
	const X1 = Math.max(...N.map((n) => n.x1));
	const mf = (x: number) => 1 + 0.35 * Math.sin(Math.PI * cl((t - ((x - 1.5) / (X1 - 1.5)) * 0.9) / 0.5));
	return { d: seed().map((s) => outline(s, 1, mf)).join('') + N.map((n) => outline(n, 1, mf)).join(''), view: box(N), text: cl((t - 1.0) / 0.4) };
}

/** Malá značka po doběhnutí běhu: samotným E projde vlna od kořene k ramenům (~1 s). */
export function wave(t: number): Frame {
	const mf = (x: number) => 1 + 0.3 * Math.sin(Math.PI * cl((t - ((x - 1.5) / 24.5) * 0.5) / 0.5));
	return { d: seed().map((s) => outline(s, 1, mf)).join(''), view: MARK_VIEW, text: cl(t / 0.4) };
}

/** Přerušený běh: spodní větev uschne, zúží se a skloní (~1,3 s). */
export function wither(t: number): Frame {
	const S = seed(), e = io(cl(t / 1.2)), a = S[7], b = S[6], w = 3.4 * (1 - 0.45 * e);
	b.w1 = w;
	a.w0 = w;
	a.w1 = 2.8 * (1 - 0.88 * e);
	a.y1 = 26.5 + 2.2 * e;
	a.x1 = 26 - 0.8 * e;
	return { d: S.map((s) => outline(s)).join(''), view: MARK_VIEW, text: cl((t - 0.9) / 0.4) };
}

/** Rodokmen podle postupu p ∈ ⟨0, 1⟩ s pevným záběrem (běh simulace). */
export function progress(p: number, sd = 23): Frame {
	const N = build(sd), Tend = Math.max(...N.map((n) => n.end ?? 0)), t = 0.8 + p * (Tend - 0.8);
	let d = seed().map((s) => outline(s)).join('');
	for (const n of N) {
		const q = eo(cl((t - (n.start ?? 0)) / (n.dur ?? 1)));
		if (q > 0) d += outline(n, q);
	}
	return { d, view: box(N), text: 1 };
}

/** Úvodní animace: E se nadechne, vyroste do rodokmenu, část větví vymře, kamera se oddaluje
 *  a předbíhá růst, na konci projde vlna. Vrací funkci snímku a délku (s). */
export function splash(sd = 23) {
	const N = build(sd), Tend = Math.max(...N.map((n) => n.end ?? 0)), tw = Tend + 0.2, X0 = 1.5, X1 = Math.max(...N.map((n) => n.x1));
	let cam: View = [...MARK_VIEW], last = -1;
	const frame = (t: number) => {
		const dt = last < 0 ? 0 : Math.min(0.05, Math.max(0, t - last));
		last = t;
		const mf = (x: number) => 1 + 0.32 * Math.sin(Math.PI * cl((t - tw - ((x - X0) / (X1 - X0)) * 0.9) / 0.55));
		let d = seed().map((s) => outline(s, 1, mf)).join(''), bx0 = 1.5, by0 = 4.4, bx1 = 26, by1 = 28.2;
		for (const n of N) {
			const p = eo(cl((t - (n.start ?? 0)) / (n.dur ?? 1)));
			if (p <= 0) continue;
			n.k = n.ext ? 1 - 0.75 * eo(cl((t - (n.end ?? 0) - 0.3) / 0.5)) : 1;
			d += outline(n, p, mf);
			bx0 = Math.min(bx0, n.x1);
			bx1 = Math.max(bx1, n.x1 + 2);
			by0 = Math.min(by0, n.y1 - 2);
			by1 = Math.max(by1, n.y1 + 2);
		}
		const breath = 1 - 0.06 * Math.sin(Math.PI * cl(t / 0.8));
		const sz = Math.max(MARK_VIEW[2], bx1 - bx0 + 12, by1 - by0 + 12) * breath;
		const target: View = [(bx0 + bx1) / 2 - 0.6 - sz / 2, (by0 + by1) / 2 - sz / 2, sz];
		const k = dt === 0 ? (t > 0.05 ? 1 : 0) : 1 - Math.exp(-dt * 3.2);
		cam = [cam[0] + (target[0] - cam[0]) * k, cam[1] + (target[1] - cam[1]) * k, cam[2] + (target[2] - cam[2]) * k];
		return {
			d,
			view: cam,
			/** číslo generace pro průvodní text */
			generation: Math.round(412 * eo(cl((t - 0.8) / (Tend - 0.8)))),
			/** 0–1: nápis CEE (text generace zároveň mizí) */
			text: cl((t - tw - 1.1) / 0.6)
		};
	};
	return { frame, length: tw + 2.6 };
}
