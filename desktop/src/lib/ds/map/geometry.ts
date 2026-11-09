// Geometrie mapy světa (převzato z prototypu docs/ui-navrh/zdroje/aplikace/template.html).
// Pevnina z kostry spojů sousedních krajů a alfa-tvaru, pokřivená šumem; reliéf podle terénu.
import { Delaunay } from 'd3-delaunay';

export interface MapRegion {
	id: string;
	name: string;
	position: [number, number];
	terrain?: string | null;
	neighbours?: string[];
}
export interface MapVillage {
	id: string;
	region: string;
	x: number;
	y: number;
}

export function hash(i: number, j: number): number {
	let h = Math.imul(i, 374761393) + Math.imul(j, 668265263);
	h = Math.imul(h ^ (h >>> 13), 1274126177);
	return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
export function vnoise(x: number, y: number): number {
	const i = Math.floor(x), j = Math.floor(y), fx = x - i, fy = y - j, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
	const a = hash(i, j), b = hash(i + 1, j), c = hash(i, j + 1), d = hash(i + 1, j + 1);
	return (a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v) * 2 - 1;
}
export function fbm(x: number, y: number): number {
	return vnoise(x, y) * 0.55 + vnoise(x * 2.1 + 17, y * 2.1 - 9) * 0.3 + vnoise(x * 4.3 - 5, y * 4.3 + 23) * 0.15;
}
function segDist(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
	const dx = bx - ax, dy = by - ay, l = dx * dx + dy * dy;
	const t = l ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l)) : 0;
	return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}
type P = [number, number];
function triDist(x: number, y: number, [a, b, c]: [P, P, P]): number {
	const s1 = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]);
	const s2 = (c[0] - b[0]) * (y - b[1]) - (c[1] - b[1]) * (x - b[0]);
	const s3 = (a[0] - c[0]) * (y - c[1]) - (a[1] - c[1]) * (x - c[0]);
	if ((s1 >= 0 && s2 >= 0 && s3 >= 0) || (s1 <= 0 && s2 <= 0 && s3 <= 0)) return 0;
	return Math.min(segDist(x, y, a[0], a[1], b[0], b[1]), segDist(x, y, b[0], b[1], c[0], c[1]), segDist(x, y, c[0], c[1], a[0], a[1]));
}

const TERRAIN_HEIGHT: Record<string, number> = { mountains: 1, hills: 0.42, island: 0.16, plain: 0.05 };

export interface Geo {
	/** typická vzdálenost sousedních krajů (km); měřítko pobřeží, reliéfu a hranic */
	D: number;
	/** měřítko vůči prototypu (Poloostrov = 1) */
	K: number;
	landField(x: number, y: number): number;
	height(x: number, y: number): number;
}

export function buildGeo(regions: MapRegion[], villages: MapVillage[]): Geo {
	const byId = new Map(regions.map((r) => [r.id, r]));
	const dist: number[] = [];
	for (const r of regions)
		for (const n of r.neighbours ?? []) {
			const o = byId.get(n);
			if (o) dist.push(Math.hypot(r.position[0] - o.position[0], r.position[1] - o.position[1]));
		}
	dist.sort((a, b) => a - b);
	const K = Math.max(0.08, Math.min(2, (dist[dist.length >> 1] || 45) / 45));
	const D = 45 * K;

	const skel: [number, number, number, number][] = [];
	const isl: P[] = [];
	for (const r of regions) {
		if (r.terrain === 'island') {
			isl.push(r.position);
			continue;
		}
		for (const n of r.neighbours ?? []) {
			const o = byId.get(n);
			if (!o || o.terrain === 'island' || o.id < r.id) continue;
			if (Math.hypot(o.position[0] - r.position[0], o.position[1] - r.position[1]) > 2.6 * D) continue;
			skel.push([r.position[0], r.position[1], o.position[0], o.position[1]]);
		}
		skel.push([r.position[0], r.position[1], r.position[0], r.position[1]]);
	}
	const tri: [P, P, P][] = [];
	const main = regions.filter((r) => r.terrain !== 'island').map((r) => r.position);
	if (main.length >= 3) {
		const del = Delaunay.from(main);
		for (let t = 0; t < del.triangles.length; t += 3) {
			const p = [0, 1, 2].map((q) => main[del.triangles[t + q]]) as [P, P, P];
			const e = Math.max(
				Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]),
				Math.hypot(p[1][0] - p[2][0], p[1][1] - p[2][1]),
				Math.hypot(p[2][0] - p[0][0], p[2][1] - p[0][1])
			);
			if (e <= 3.4 * D) tri.push(p);
		}
	}
	const vpts: P[] = villages.map((v) => [v.x, v.y]);

	function landField(x: number, y: number): number {
		const wx = x + fbm(x / (1.3 * D), y / (1.3 * D)) * 0.45 * D;
		const wy = y + fbm(x / (1.3 * D) + 40, y / (1.3 * D) + 11) * 0.45 * D;
		let d = Infinity;
		for (const [ax, ay, bx, by] of skel) {
			const q = segDist(wx, wy, ax, ay, bx, by);
			if (q < d) d = q;
		}
		for (const t of tri) {
			if (d === 0) break;
			const q = triDist(wx, wy, t);
			if (q < d) d = q;
		}
		let di = Infinity;
		for (const [ix, iy] of isl) {
			const q = Math.hypot(wx - ix, wy - iy);
			if (q < di) di = q;
		}
		let dv = Infinity;
		for (const [vx, vy] of vpts) {
			const q = Math.hypot(x - vx, y - vy);
			if (q < dv) dv = q;
		}
		const rough = fbm(x / (0.35 * D) + 3, y / (0.35 * D) - 7) * 0.16 * D;
		return Math.max(0.58 * D - d + rough, 0.5 * D - di + rough, 0.32 * D - dv);
	}
	const sig = 0.62 * D;
	function height(x: number, y: number): number {
		let h = 0;
		for (const r of regions) {
			const dx = x - r.position[0], dy = y - r.position[1], q = dx * dx + dy * dy;
			if (q < 9 * sig * sig) h += (TERRAIN_HEIGHT[r.terrain ?? 'plain'] ?? 0.05) * Math.exp(-q / (2 * sig * sig));
		}
		const t = Math.min(1, h);
		return h + (0.02 + 0.32 * t) * fbm(x / (0.4 * D), y / (0.4 * D)) + 0.06 * t * fbm(x / (0.13 * D) + 9, y / (0.13 * D) - 4);
	}
	return { D, K, landField, height };
}

/** Zvlněná hrana mezi dvěma body; obě sousední buňky dostanou stejnou čáru. */
export function wobble(ax: number, ay: number, bx: number, by: number): P[] {
	const flip = ax > bx || (ax === bx && ay > by);
	if (flip) [ax, ay, bx, by] = [bx, by, ax, ay];
	const len = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.min(14, Math.round(len / 5)));
	const nx = -(by - ay) / (len || 1), ny = (bx - ax) / (len || 1);
	const seed = hash(Math.round(ax * 2 + bx * 3), Math.round(ay * 2 + by * 3)) * 100, amp = Math.min(0.16 * len, 5);
	const pts: P[] = [];
	for (let t = 0; t <= n; t++) {
		const u = t / n, w = Math.sin(Math.PI * u) * (vnoise(seed + u * 2.2, seed * 0.7) + vnoise(seed + u * 6, seed) * 0.35) * amp;
		pts.push([ax + (bx - ax) * u + nx * w, ay + (by - ay) * u + ny * w]);
	}
	return flip ? pts.reverse() : pts;
}
