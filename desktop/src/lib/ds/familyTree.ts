// Rozvržení evolučního stromu rodiny (FamilyTree): osa x = čas, každý jazyk má svůj řádek,
// potomek odbočí křivkou S v roce vzniku (ne dřív, než rodič dorazí na svůj řádek), tloušťka konce
// odpovídá √mluvčích, vymřelý jazyk se zúží do vlásečnice. Dřívější odbočky leží dál od rodiče,
// takže se větve skoro nekříží. Stejná geometrie jako značka CEE (obrys křivky s proměnnou tloušťkou).

export interface TreeLineage {
	id: string;
	parent: string | null;
	start: number;
	/** rok zániku; null = žije */
	end: number | null;
	/** mluvčí na konci (pro tloušťku) */
	speakers: number;
}
export interface TreeBranch {
	id: string;
	/** obrys větve (jeden vyplněný tvar) */
	d: string;
	/** konec větve, kam patří popisek */
	x: number;
	y: number;
	extinct: boolean;
}
export interface TreeLayout {
	branches: TreeBranch[];
	width: number;
	height: number;
	x: (year: number) => number;
	from: number;
	to: number;
}

interface Node extends TreeLineage {
	kids: Node[];
	row: number;
	rowX: number;
}
interface Seg {
	x0: number;
	y0: number;
	x1: number;
	y1: number;
	w: (x: number) => number;
}

function outline(s: Seg) {
	const N = s.y0 === s.y1 ? 2 : 32, L: [number, number][] = [], R: [number, number][] = [];
	for (let i = 0; i <= N; i++) {
		const t = i / N, m = (s.x0 + s.x1) / 2, u = 1 - t;
		const x = u * u * u * s.x0 + 3 * u * u * t * m + 3 * u * t * t * m + t * t * t * s.x1;
		const y = u * u * u * s.y0 + 3 * u * u * t * s.y0 + 3 * u * t * t * s.y1 + t * t * t * s.y1;
		let dx = 3 * u * u * (m - s.x0) + 3 * t * t * (s.x1 - m), dy = 6 * u * t * (s.y1 - s.y0);
		const n = Math.hypot(dx, dy) || 1;
		dx /= n;
		dy /= n;
		const w = s.w(x) / 2;
		L.push([x - dy * w, y + dx * w]);
		R.push([x + dy * w, y - dx * w]);
	}
	return 'M' + L.concat(R.reverse()).map((q) => q[0].toFixed(1) + ' ' + q[1].toFixed(1)).join('L') + 'Z';
}

/** Rozvrhne rodiny do plochy šířky `width` (bez popisků) s výškou řádku `rowH`. */
export function familyTree(lineages: TreeLineage[], now: number, width: number, rowH: number): TreeLayout {
	const byId = new Map<string, Node>(lineages.map((l) => [l.id, { ...l, kids: [], row: 0, rowX: 0 }]));
	for (const n of byId.values()) if (n.parent && byId.has(n.parent)) byId.get(n.parent)!.kids.push(n);
	for (const n of byId.values()) n.kids.sort((a, b) => a.start - b.start);
	const size = (n: Node): number => 1 + n.kids.reduce((s, k) => s + size(k), 0);
	const roots = [...byId.values()].filter((n) => !n.parent || !byId.has(n.parent)).sort((a, b) => size(b) - size(a));
	// děti střídavě nad a pod rodičem, dřívější rozštěpení dál od osy rodiče
	const rows = (n: Node): Node[] => {
		const up: Node[] = [], dn: Node[] = [];
		n.kids.forEach((k, i) => (i % 2 ? dn : up).push(k));
		return [...up.flatMap(rows), n, ...dn.reverse().flatMap(rows)];
	};
	let r = 0;
	for (const root of roots) {
		for (const n of rows(root)) n.row = r++;
		r += 0.8; // mezera mezi rodinami
	}
	const all = [...byId.values()];
	const from = Math.min(...all.map((n) => n.start)), to = now;
	const X = (y: number) => ((y - from) / (to - from || 1)) * width, Y = (row: number) => row * rowH;
	const wmax = Math.min(12, rowH * 0.55), wmin = Math.min(3.5, rowH * 0.18), thin = Math.max(0.6, rowH * 0.04);
	const maxPop = Math.max(1, ...all.map((n) => (n.end == null ? n.speakers : 0)));
	const wEnd = (n: Node) => (n.end != null ? thin : wmin + (wmax - wmin) * Math.sqrt(n.speakers / maxPop));
	const out: TreeBranch[] = [];
	const walk = (n: Node, parentW: number | null) => {
		// kořen začíná tloušťkou podle velikosti rodiny (osamělý krátký jazyk nemá být klín)
		const xs = X(n.start), w1 = wEnd(n), w0 = parentW ?? Math.max(w1, Math.min(wmax, wmin * 1.3 + (size(n) - 1) * wmax * 0.25));
		let xe = X(n.end ?? now);
		const wAt = (x: number) => w0 + (w1 - w0) * Math.max(0, Math.min(1, (x - xs) / Math.max(1e-6, xe - xs)));
		const segs: Seg[] = [];
		n.rowX = xs;
		const p = n.parent ? byId.get(n.parent) : undefined;
		if (p) {
			const yp = Y(p.row), yc = Y(n.row), a = Math.max(xs, p.rowX), dx = Math.max(rowH * 0.9, Math.abs(yc - yp) * 0.9), b = Math.max(xe, a + dx);
			n.rowX = a + dx;
			segs.push({ x0: a, y0: yp, x1: a + dx, y1: yc, w: wAt });
			if (b > a + dx) segs.push({ x0: a + dx, y0: yc, x1: b, y1: yc, w: wAt });
			xe = b;
		} else segs.push({ x0: xs, y0: Y(n.row), x1: xe, y1: Y(n.row), w: wAt });
		out.push({ id: n.id, d: segs.map(outline).join(''), x: xe, y: Y(n.row), extinct: n.end != null });
		for (const k of n.kids) walk(k, Math.min(wAt(X(k.start)), wmax) * 0.85);
	};
	for (const root of roots) walk(root, null);
	return { branches: out, width, height: Y(Math.max(0, r - 1.8)), x: X, from, to };
}
