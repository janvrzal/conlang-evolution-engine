<!-- Mapa světa: pevnina z kostry krajů, reliéf podle terénu, buňky vsí a krajů s přírodními hranicemi.
     Obrazovka dodá jen barvy, šrafy, styl hran, popisky a značky; kreslení a geometrie jsou tady.
     Klávesnice: šipky přecházejí mezi sousedními kraji, Enter vybere. -->
<script lang="ts">
	import { Delaunay, type Voronoi } from 'd3-delaunay';
	import { contours } from 'd3-contour';
	import { onMount, untrack } from 'svelte';
	import { cssVar } from './color';
	import { T, change, still } from './motion';
	import { buildGeo, wobble, type MapRegion, type MapVillage } from './map/geometry';

	/** Barva v mapě: token ('ink' | 'muted' | 'red') nebo konkrétní barva. */
	export type MapColor = 'ink' | 'muted' | 'red' | (string & {});
	export interface EdgeStyle {
		color?: MapColor;
		width?: number;
		/** state = čerchovaně (hranice států), dotted, dashed, nebo plná */
		dash?: 'state' | 'dotted' | 'dashed' | null;
		alpha?: number;
	}
	export interface Hatch {
		angle: number;
		color?: MapColor;
		gap?: number;
		width?: number;
	}
	export interface MapLabel {
		text: string;
		/** kotva: kraj, skupina vsí (těžiště) nebo souřadnice světa */
		region?: string;
		villages?: string[];
		x?: number;
		y?: number;
		kind?: 'region' | 'language' | 'state' | 'strong';
		/** výslovnost: písmo Charis, bez převodu na velká písmena */
		ipa?: boolean;
		/** kurzíva (slovo z jiné rodiny) */
		italic?: boolean;
		/** posun dolů v px */
		dy?: number;
	}
	export interface MapMarker {
		region?: string;
		village?: string;
		kind: 'city' | 'capital' | 'dot';
	}
	export interface MapArrow {
		from: string;
		to: string;
		dashed?: boolean;
	}
	/** Úprava mapy (obrazovka Svět): režim nástroje a co se má stát. Souřadnice jsou ve světě (km). */
	export interface MapEdit {
		mode: 'select' | 'add' | 'move' | 'link';
		/** klik v režimu add */
		onadd?: (x: number, y: number) => void;
		/** puštění taženého kraje v režimu move */
		onmove?: (region: string, x: number, y: number) => void;
		/** dva kraje kliknuté po sobě v režimu link (přepne sousedství) */
		onlink?: (a: string, b: string) => void;
	}

	let {
		regions,
		villages,
		label,
		summary,
		fill,
		fillAlpha = 0.55,
		regionFill,
		hatch,
		regionHatch,
		edge,
		highlight = [],
		selected = null,
		labels = [],
		markers = [],
		arrows = [],
		focus = null,
		relief = true,
		edit = null,
		onpick,
		onhover
	}: {
		regions: MapRegion[];
		villages: MapVillage[];
		/** krátký popis pro čtečku (aria-label) */
		label: string;
		/** textový souhrn mapy pro čtečku (co je na ní vidět) */
		summary?: string;
		/** barva vsi (jazyk doma); null = bez výplně */
		fill?: (village: MapVillage) => string | null;
		fillAlpha?: number;
		/** výplň kraje (stát) */
		regionFill?: (region: MapRegion) => { color: MapColor; alpha?: number } | null;
		hatch?: (village: MapVillage) => Hatch | null;
		regionHatch?: (region: MapRegion) => Hatch | null;
		/** styl hrany mezi dvěma sousedními vesmi (hranice kraje, státu, izoglosa, rozdíl) */
		edge?: (a: MapVillage, b: MapVillage) => EdgeStyle | null;
		/** kraje zvýrazněné červeně (událost, náhled opravy) */
		highlight?: string[];
		/** vybraný kraj (obrys inkoustem) */
		selected?: string | null;
		labels?: MapLabel[];
		markers?: MapMarker[];
		arrows?: MapArrow[];
		/** přiblížit na tyto vsi; null = celý svět */
		focus?: string[] | null;
		relief?: boolean;
		/** editační režim: středy krajů a vazby sousedů, přidání, posun, spojení */
		edit?: MapEdit | null;
		onpick?: (region: string, village: string) => void;
		onhover?: (hit: { region: string; village: string; x: number; y: number } | null) => void;
	} = $props();

	const uid = $props.id();
	let stage: HTMLDivElement;
	let canvas: HTMLCanvasElement;
	let keyRegion = $state<string | null>(null);
	/** tažený kraj (v px) a první kraj spojení */
	let drag = $state<{ region: string; x: number; y: number } | null>(null);
	let linkFrom = $state<string | null>(null);
	let pointer = $state<[number, number] | null>(null);
	$effect(() => {
		// při změně nástroje se rozpracované spojení zahodí
		void edit?.mode;
		linkFrom = null;
	});

	interface Layout {
		W: number;
		H: number;
		dpr: number;
		P: (x: number, y: number) => [number, number];
		/** z px na plátně do souřadnic světa */
		inv: (px: number, py: number) => [number, number];
		land: Path2D;
		rings: Path2D[];
		shade: HTMLCanvasElement | null;
		vcells: Path2D[];
		/** poloměr buňky vsi (nejvzdálenější roh od vsi) */
		vrad: number[];
		rcells: Map<string, Path2D>;
		vpts: [number, number][];
		rpts: Map<string, [number, number]>;
		vdel: Delaunay<[number, number]>;
		edges: { a: number; b: number; x1: number; y1: number; x2: number; y2: number }[];
		/** obyčejné kopie vsí ve stejném pořadí jako buňky */
		vil: MapVillage[];
	}
	let layout = $state.raw<Layout | null>(null);

	const color = (c: MapColor | undefined, fallback = 'ink') => {
		const v = c ?? fallback;
		return v === 'ink' ? cssVar('--ink') : v === 'muted' ? cssVar('--ink-2') : v === 'red' ? cssVar('--red') : v;
	};

	function polyPath(pg: ArrayLike<[number, number]> | null | undefined): Path2D {
		const p = new Path2D();
		if (!pg) return p;
		for (let n = 0; n < pg.length - 1; n++) {
			const seg = wobble(pg[n][0], pg[n][1], pg[n + 1][0], pg[n + 1][1]);
			seg.forEach(([x, y], q) => (n === 0 && q === 0 ? p.moveTo(x, y) : p.lineTo(x, y)));
		}
		p.closePath();
		return p;
	}

	// Přepočet geometrie je drahý: víc podnětů v jednom snímku (velikost, data) se sloučí do jednoho.
	let pending = 0;
	function schedule() {
		cancelAnimationFrame(pending);
		pending = requestAnimationFrame(() => untrack(build));
	}

	function build() {
		if (!stage || !villages.length || !regions.length) return;
		// obyčejné kopie: čtení reaktivních objektů v horké smyčce by stálo sledování závislostí
		const regions_ = regions.map((r) => ({ id: r.id, name: r.name, position: [+r.position[0], +r.position[1]] as [number, number], terrain: r.terrain ?? null, neighbours: [...(r.neighbours ?? [])] }));
		const villages_ = villages.map((v) => ({ id: v.id, region: v.region, x: +v.x, y: +v.y }));
		const W = stage.clientWidth, H = stage.clientHeight;
		if (!W || !H) return;
		const dpr = Math.min(2, window.devicePixelRatio || 1);
		canvas.width = Math.round(W * dpr);
		canvas.height = Math.round(H * dpr);
		canvas.style.width = `${W}px`;
		canvas.style.height = `${H}px`;
		const geo = buildGeo(regions_, villages_);
		const focusSet = focus?.length ? new Set(focus) : null;
		const frame = focusSet ? villages_.filter((v) => focusSet.has(v.id)) : villages_;
		const pad = (focusSet ? 95 : 44) * geo.K;
		const xs = frame.map((v) => v.x), ys = frame.map((v) => v.y);
		const minx = Math.min(...xs) - pad, maxx = Math.max(...xs) + pad, miny = Math.min(...ys) - pad, maxy = Math.max(...ys) + pad;
		const k = Math.min((W - 20) / (maxx - minx), (H - 20) / (maxy - miny));
		const ox = (W - k * (maxx - minx)) / 2 - k * minx, oy = (H - k * (maxy - miny)) / 2 - k * miny;
		const P = (x: number, y: number): [number, number] => [ox + k * x, oy + k * y];

		// pevnina a pásy mělčiny z pole vzdálenosti
		const g = 3, nx = Math.ceil(W / g) + 1, ny = Math.ceil(H / g) + 1, values = new Float64Array(nx * ny);
		for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) values[j * nx + i] = geo.landField((i * g - ox) / k, (j * g - oy) / k);
		const K = geo.K;
		const cs = contours().size([nx, ny]).thresholds([0, -5 * K, -11 * K, -18 * K])(Array.from(values)).sort((a, b) => b.value - a.value);
		const toPath = (mp: { coordinates: number[][][][] }) => {
			const p = new Path2D();
			for (const poly of mp.coordinates)
				for (const ring of poly) ring.forEach(([x, y], n) => (n ? p.lineTo(x * g, y * g) : p.moveTo(x * g, y * g)));
			return p;
		};
		const land = toPath(cs[0]);
		const rings = cs.slice(1).map(toPath);

		// reliéf: stín ze severozápadu podle výšky terénu
		let shade: HTMLCanvasElement | null = null;
		if (relief) {
			const hgt = new Float32Array(nx * ny);
			for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) hgt[j * nx + i] = geo.height((i * g - ox) / k, (j * g - oy) / k);
			shade = document.createElement('canvas');
			shade.width = nx;
			shade.height = ny;
			const sx = shade.getContext('2d')!, img = sx.createImageData(nx, ny);
			for (let j = 1; j < ny - 1; j++)
				for (let i = 1; i < nx - 1; i++) {
					const o = j * nx + i;
					if (values[o] < 0) continue;
					const lit = (-(hgt[o + 1] - hgt[o - 1]) * 0.7 - (hgt[o + nx] - hgt[o - nx]) * 0.7) * 2.2, p = o * 4;
					if (lit < 0) img.data.set([40, 52, 60, Math.min(115, -lit * 200)], p);
					else img.data.set([255, 255, 250, Math.min(80, lit * 140)], p);
				}
			sx.putImageData(img, 0, 0);
		}

		// buňky vsí; kraj = sjednocení buněk jeho vsí
		const vpts = villages_.map((v) => P(v.x, v.y));
		const vdel = Delaunay.from(vpts);
		const vvor: Voronoi<[number, number]> = vdel.voronoi([0, 0, W, H]);
		const vcells = villages_.map((_, i) => polyPath(vvor.cellPolygon(i) as [number, number][]));
		const vrad = villages_.map((_, i) => {
			const pg = vvor.cellPolygon(i) ?? [];
			let r = 0;
			for (const [x, y] of pg) r = Math.max(r, Math.hypot(x - vpts[i][0], y - vpts[i][1]));
			return r;
		});
		const rcells = new Map<string, Path2D>();
		villages_.forEach((v, i) => {
			if (!rcells.has(v.region)) rcells.set(v.region, new Path2D());
			rcells.get(v.region)!.addPath(vcells[i]);
		});
		const rpts = new Map(regions_.map((r) => [r.id, P(...r.position)] as const));
		const edges: Layout['edges'] = [];
		const { halfedges, triangles } = vdel, cc = vvor.circumcenters;
		for (let e = 0; e < halfedges.length; e++) {
			const o = halfedges[e];
			if (o < e) continue;
			const a = triangles[e], b = triangles[e % 3 === 2 ? e - 2 : e + 1], t1 = Math.floor(e / 3), t2 = Math.floor(o / 3);
			edges.push({ a, b, x1: cc[2 * t1], y1: cc[2 * t1 + 1], x2: cc[2 * t2], y2: cc[2 * t2 + 1] });
		}
		const inv = (px: number, py: number): [number, number] => [(px - ox) / k, (py - oy) / k];
		layout = { W, H, dpr, P, inv, land, rings, shade, vcells, vrad, rcells, vpts, rpts, vdel, edges, vil: villages_ };
	}

	function hatchPath(c: CanvasRenderingContext2D, path: Path2D, h: Hatch) {
		c.save();
		c.clip(path);
		c.strokeStyle = color(h.color, 'muted');
		c.lineWidth = h.width ?? 0.8;
		c.beginPath();
		const d = Math.hypot(c.canvas.width, c.canvas.height), s = Math.sin(h.angle), co = Math.cos(h.angle);
		for (let t = -d; t < d; t += h.gap ?? 7) {
			c.moveTo(t * co - d * s, t * s + d * co);
			c.lineTo(t * co + d * s, t * s - d * co);
		}
		c.stroke();
		c.restore();
	}
	function strokeEdge(c: CanvasRenderingContext2D, e: { x1: number; y1: number; x2: number; y2: number }, part = 1) {
		let p = wobble(e.x1, e.y1, e.x2, e.y2);
		if (part < 1) {
			// jen začátek hrany (dokreslování): poslední bod se dopočítá mezi sousedními
			const at = part * (p.length - 1), i = Math.floor(at), f = at - i;
			p = p.slice(0, i + 1);
			const a = p[i], b = wobble(e.x1, e.y1, e.x2, e.y2)[i + 1];
			if (b) p.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]);
		}
		c.beginPath();
		p.forEach(([x, y], n) => (n ? c.lineTo(x, y) : c.moveTo(x, y)));
		c.stroke();
	}
	function outline(c: CanvasRenderingContext2D, L: Layout, region: string) {
		for (const e of L.edges) {
			const ra = L.vil[e.a].region, rb = L.vil[e.b].region;
			if (ra !== rb && (ra === region || rb === region)) strokeEdge(c, e);
		}
	}
	function text(c: CanvasRenderingContext2D, t: string, x: number, y: number, font: string, spacing: string, fillColor: string) {
		c.font = font;
		c.letterSpacing = spacing;
		c.textAlign = 'center';
		c.textBaseline = 'middle';
		c.lineWidth = 4;
		c.lineJoin = 'round';
		c.strokeStyle = cssVar('--land');
		c.strokeText(t, x, y);
		c.fillStyle = fillColor;
		c.fillText(t, x, y);
		c.letterSpacing = '0px';
	}

	// Vlna změny: když se barva vsí změní, nová barva se šíří od vsí, které ji už měly (soused po sousedovi),
	// a do každé buňky vteče kruhem ze strany, odkud přišla. Nová inovace začne ve vsi uprostřed změny.
	interface Wave {
		from: string | null;
		cx: number;
		cy: number;
		r0: number;
		r1: number;
		t0: number;
	}
	let wavesOf: Layout | null = null;
	let prevFill: (string | null)[] = [];
	const waves = new Map<number, Wave>();
	let waveFrame = 0;
	// Nové hranice (izoglosy) u vsí, kterými prochází vlna, se dokreslí tahem, až vlna dorazí.
	let prevEdges: Set<string> | null = null;
	const edgeDraw = new Map<string, number>();
	const EDGE_MS = 450;
	function spread(L: Layout, prev: (string | null)[], next: (string | null)[], now: number) {
		const n = next.length, changed: number[] = [];
		for (let i = 0; i < n; i++) if (prev[i] !== next[i]) changed.push(i);
		// přebarvení skoro celé mapy (jiná vrstva, jiný jazyk) není šíření: bez vlny
		if (!changed.length) return;
		if (changed.length > n * 0.6) {
			waves.clear();
			return;
		}
		const isCh = new Uint8Array(n), hop = new Int32Array(n).fill(-1), src = new Int32Array(n).fill(-1);
		for (const i of changed) isCh[i] = 1;
		const queue: number[] = [];
		for (const i of changed)
			for (const j of L.vdel.neighbors(i))
				if (!isCh[j] && next[i] != null && prev[j] === next[i]) {
					hop[i] = 0;
					src[i] = j;
					queue.push(i);
					break;
				}
		const bfs = () => {
			for (let q = 0; q < queue.length; q++) {
				const i = queue[q];
				for (const j of L.vdel.neighbors(i))
					if (isCh[j] && hop[j] < 0) {
						hop[j] = hop[i] + 1;
						src[j] = i;
						queue.push(j);
					}
			}
		};
		bfs();
		const deg = (i: number) => {
			let d = 0;
			for (const j of L.vdel.neighbors(i)) d += isCh[j];
			return d;
		};
		for (;;) {
			let seed = -1, best = -1;
			for (const i of changed) if (hop[i] < 0 && deg(i) > best) [seed, best] = [i, deg(i)];
			if (seed < 0) break;
			hop[seed] = 0;
			queue.push(seed);
			bfs();
		}
		let maxHop = 0;
		for (const i of changed) maxHop = Math.max(maxHop, hop[i]);
		const step = Math.min(70, (T.epoch * 0.75) / Math.max(1, maxHop));
		for (const i of changed) {
			const [cx, cy] = L.vpts[src[i] >= 0 ? src[i] : i], d = Math.hypot(cx - L.vpts[i][0], cy - L.vpts[i][1]);
			waves.set(i, { from: prev[i], cx, cy, r0: Math.max(0, d - L.vrad[i]), r1: d + L.vrad[i], t0: now + hop[i] * step });
		}
	}

	function render() {
		const L = layout;
		if (!L || !canvas) return;
		const c = canvas.getContext('2d')!;
		const vIndex = new Map(L.vil.map((v, i) => [v.id, i]));
		c.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);
		c.fillStyle = cssVar('--sea');
		c.fillRect(0, 0, L.W, L.H);
		c.strokeStyle = cssVar('--sea-line');
		c.lineWidth = 1;
		for (const r of L.rings) c.stroke(r);
		c.fillStyle = cssVar('--land');
		c.fill(L.land);

		c.save();
		c.clip(L.land);
		if (regionFill)
			for (const r of untrack(() => regions)) {
				const f = regionFill(r), cell = L.rcells.get(r.id);
				if (!f || !cell) continue;
				c.globalAlpha = f.alpha ?? 0.16;
				c.fillStyle = color(f.color);
				c.fill(cell);
				c.globalAlpha = 1;
			}
		if (fill) {
			const now = performance.now();
			const next = L.vil.map((v) => fill(v));
			if (wavesOf !== L || prevFill.length !== next.length || still()) waves.clear();
			else spread(L, prevFill, next, now);
			wavesOf = L;
			prevFill = next;
			const paint = (f: string, i: number) => {
				c.globalAlpha = fillAlpha;
				c.fillStyle = f;
				c.fill(L.vcells[i]);
				c.globalAlpha = 1;
			};
			next.forEach((f, i) => {
				const w = waves.get(i);
				if (w) {
					const p = (now - w.t0) / T.flow;
					if (p < 1) {
						const r = p <= 0 ? 0 : w.r0 + (w.r1 - w.r0) * change(p);
						if (w.from) {
							c.save();
							if (r > 0) {
								const out = new Path2D();
								out.rect(0, 0, L.W, L.H);
								out.arc(w.cx, w.cy, r, 0, Math.PI * 2);
								c.clip(out, 'evenodd');
							}
							paint(w.from, i);
							c.restore();
						}
						if (f && r > 0) {
							c.save();
							const disk = new Path2D();
							disk.arc(w.cx, w.cy, r, 0, Math.PI * 2);
							c.clip(disk);
							paint(f, i);
							c.restore();
						}
						return;
					}
					waves.delete(i);
				}
				if (f) paint(f, i);
			});
			cancelAnimationFrame(waveFrame);
			if (waves.size) waveFrame = requestAnimationFrame(() => render());
		}
		if (regionHatch)
			for (const r of regions) {
				const h = regionHatch(r), cell = L.rcells.get(r.id);
				if (h && cell) hatchPath(c, cell, h);
			}
		if (hatch)
			L.vil.forEach((v, i) => {
				const h = hatch(v);
				if (h) hatchPath(c, L.vcells[i], h);
			});
		if (relief && L.shade) {
			c.imageSmoothingEnabled = true;
			c.drawImage(L.shade, 0, 0, L.W, L.H);
		}
		if (edge) {
			// nejdřív slabé, pak výrazné, aby červené čáry ležely nahoře
			const styled = L.edges.map((e) => ({ e, s: edge(L.vil[e.a], L.vil[e.b]) })).filter((x) => x.s);
			styled.sort((p, q) => (p.s!.color === 'red' ? 1 : 0) - (q.s!.color === 'red' ? 1 : 0) || (p.s!.width ?? 1) - (q.s!.width ?? 1));
			const now = performance.now(), keys = new Set<string>();
			for (const { e, s } of styled) {
				const key = `${e.a}-${e.b}:${s!.color ?? ''}:${s!.dash ?? ''}`;
				keys.add(key);
				if (prevEdges && !prevEdges.has(key) && !edgeDraw.has(key) && (waves.has(e.a) || waves.has(e.b)))
					edgeDraw.set(key, Math.max(waves.get(e.a)?.t0 ?? 0, waves.get(e.b)?.t0 ?? 0) + T.flow * 0.5);
			}
			prevEdges = wavesOf === L && !still() ? keys : null;
			for (const { e, s } of styled) {
				const key = `${e.a}-${e.b}:${s!.color ?? ''}:${s!.dash ?? ''}`, start = edgeDraw.get(key);
				let part = 1;
				if (start != null) {
					const p = (now - start) / EDGE_MS;
					if (p >= 1) edgeDraw.delete(key);
					else if (p <= 0) continue;
					else part = change(p);
				}
				c.strokeStyle = color(s!.color);
				c.lineWidth = s!.width ?? 1;
				c.globalAlpha = s!.alpha ?? 1;
				c.lineCap = 'round';
				c.setLineDash(s!.dash === 'state' ? [8, 3, 1.5, 3] : s!.dash === 'dotted' ? [1.5, 3] : s!.dash === 'dashed' ? [5, 4] : []);
				strokeEdge(c, e, part);
			}
			c.setLineDash([]);
			c.globalAlpha = 1;
			c.lineCap = 'butt';
		}
		for (const r of highlight) {
			const cell = L.rcells.get(r);
			if (!cell) continue;
			c.fillStyle = cssVar('--tint');
			c.fill(cell);
			c.strokeStyle = cssVar('--red');
			c.lineWidth = 2;
			outline(c, L, r);
		}
		if (selected) {
			c.strokeStyle = cssVar('--ink');
			c.lineWidth = 2.6;
			outline(c, L, selected);
		}
		if (keyRegion && keyRegion !== selected) {
			c.strokeStyle = cssVar('--ink');
			c.lineWidth = 1.6;
			c.setLineDash([4, 3]);
			outline(c, L, keyRegion);
			c.setLineDash([]);
		}
		c.strokeStyle = cssVar('--sea-line');
		c.globalAlpha = 0.55;
		c.lineWidth = 6;
		c.stroke(L.land);
		c.globalAlpha = 1;
		c.restore();
		c.strokeStyle = cssVar('--ink');
		c.lineWidth = 1;
		c.stroke(L.land);

		// šipky (osídlení, elita, lingua franca)
		for (const a of arrows) {
			const p = L.rpts.get(a.from), q = L.rpts.get(a.to);
			if (!p || !q) continue;
			c.strokeStyle = cssVar('--red');
			c.lineWidth = 1.6;
			c.setLineDash(a.dashed ? [3, 3] : []);
			c.beginPath();
			c.moveTo(...p);
			c.quadraticCurveTo((p[0] + q[0]) / 2, Math.min(p[1], q[1]) - 30, ...q);
			c.stroke();
			c.setLineDash([]);
		}
		// značky
		for (const m of markers) {
			const at = m.village != null ? L.vpts[vIndex.get(m.village) ?? -1] : m.region ? L.rpts.get(m.region) : undefined;
			if (!at) continue;
			const [x, y] = at;
			if (m.kind === 'capital') {
				c.fillStyle = cssVar('--ink');
				c.fillRect(x - 3.5, y - 3.5, 7, 7);
			} else if (m.kind === 'city') {
				c.fillStyle = cssVar('--land');
				c.fillRect(x - 4, y - 4, 8, 8);
				c.strokeStyle = cssVar('--ink');
				c.lineWidth = 1.6;
				c.strokeRect(x - 4, y - 4, 8, 8);
			} else {
				c.fillStyle = cssVar('--ink-2');
				c.beginPath();
				c.arc(x, y, 2.2, 0, 7);
				c.fill();
			}
		}
		// editační režim: vazby sousedů a středy krajů (úchyty)
		if (edit && edit.mode !== 'select') {
			c.save();
			c.strokeStyle = cssVar('--ink-2');
			c.lineWidth = 1;
			c.globalAlpha = 0.55;
			for (const r of regions)
				for (const n of r.neighbours ?? []) {
					if (n < r.id) continue;
					const a = L.rpts.get(r.id), b = L.rpts.get(n);
					if (!a || !b) continue;
					c.beginPath();
					c.moveTo(...a);
					c.lineTo(...b);
					c.stroke();
				}
			c.globalAlpha = 1;
			for (const r of regions) {
				const at = L.rpts.get(r.id);
				if (!at) continue;
				const active = r.id === linkFrom || r.id === selected;
				c.beginPath();
				c.arc(at[0], at[1], active ? 6 : 4.5, 0, 7);
				c.fillStyle = active ? cssVar('--ink') : cssVar('--land');
				c.fill();
				c.strokeStyle = cssVar('--ink');
				c.lineWidth = 1.5;
				c.stroke();
			}
			if (linkFrom && pointer) {
				const a = L.rpts.get(linkFrom);
				if (a) {
					c.setLineDash([4, 3]);
					c.strokeStyle = cssVar('--ink');
					c.beginPath();
					c.moveTo(...a);
					c.lineTo(...pointer);
					c.stroke();
					c.setLineDash([]);
				}
			}
			if (drag) {
				const from = L.rpts.get(drag.region);
				c.setLineDash([4, 3]);
				c.strokeStyle = cssVar('--ink');
				if (from) {
					c.beginPath();
					c.moveTo(...from);
					c.lineTo(drag.x, drag.y);
					c.stroke();
				}
				c.setLineDash([]);
				c.beginPath();
				c.arc(drag.x, drag.y, 7, 0, 7);
				c.fillStyle = cssVar('--ink');
				c.fill();
			}
			c.restore();
		}
		// popisky bez překryvů: v pořadí, jak přišly; stát zkusí náhradní polohy, ostatní se vynechají
		const placed: [number, number, number, number][] = [];
		const STYLE = {
			region: { font: `600 8.5px ${cssVar('--f-ui')}`, spacing: '1.5px', color: cssVar('--ink-2'), upper: true },
			language: { font: `600 10px ${cssVar('--f-ui')}`, spacing: '1px', color: cssVar('--ink'), upper: true },
			state: { font: `700 10.5px ${cssVar('--f-ui')}`, spacing: '2px', color: cssVar('--ink'), upper: true },
			strong: { font: `600 11px ${cssVar('--f-ui')}`, spacing: '1.5px', color: cssVar('--ink'), upper: true }
		} as const;
		for (const l of labels) {
			const base = STYLE[l.kind ?? 'region'];
			const st = l.ipa
				? { font: `${l.italic ? 'italic ' : ''}400 14px ${cssVar('--f-ipa')}`, spacing: '0px', color: cssVar('--ink'), upper: false }
				: l.italic
					? { ...base, font: `italic ${base.font}` }
					: base;
			let at: [number, number] | undefined;
			if (l.region) at = L.rpts.get(l.region);
			else if (l.villages?.length) {
				const pts = l.villages.map((id) => L.vpts[vIndex.get(id) ?? -1]).filter(Boolean);
				if (pts.length) at = [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
			} else if (l.x != null && l.y != null) at = L.P(l.x, l.y);
			if (!at) continue;
			const t = st.upper ? l.text.toUpperCase() : l.text;
			c.font = st.font;
			c.letterSpacing = st.spacing;
			const w = c.measureText(t).width + 8;
			c.letterSpacing = '0px';
			const tries = l.kind === 'state' ? [0, -20, 18, -38, 36] : [0];
			for (const off of tries) {
				const x = at[0], y = at[1] + (l.dy ?? 0) + off;
				if (x < 0 || y < 0 || x > L.W || y > L.H) break;
				const box: [number, number, number, number] = [x - w / 2, y - 8, x + w / 2, y + 8];
				if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
				placed.push(box);
				text(c, t, x, y, st.font, st.spacing, st.color);
				break;
			}
		}
		if (edgeDraw.size && !waves.size) {
			cancelAnimationFrame(waveFrame);
			waveFrame = requestAnimationFrame(() => render());
		}
	}

	function hit(event: MouseEvent) {
		const L = layout;
		if (!L) return null;
		const r = canvas.getBoundingClientRect(), x = event.clientX - r.left, y = event.clientY - r.top;
		const i = L.vdel.find(x, y);
		return i >= 0 ? { region: L.vil[i].region, village: L.vil[i].id, x, y } : null;
	}
	/** Nejbližší střed kraje do vzdálenosti `within` px. */
	function nearestRegion(x: number, y: number, within: number): string | null {
		const L = layout;
		if (!L) return null;
		let best: string | null = null, d = within;
		for (const [id, [rx, ry]] of L.rpts) {
			const q = Math.hypot(rx - x, ry - y);
			if (q < d) [best, d] = [id, q];
		}
		return best;
	}
	function local(event: MouseEvent): [number, number] {
		const r = canvas.getBoundingClientRect();
		return [event.clientX - r.left, event.clientY - r.top];
	}
	function click(event: MouseEvent) {
		const L = layout;
		if (edit?.mode === 'add' && L) {
			edit.onadd?.(...L.inv(...local(event)));
			return;
		}
		if (edit?.mode === 'move') return;
		const h = hit(event);
		if (!h) return;
		if (edit?.mode === 'link') {
			const id = nearestRegion(...local(event), 24) ?? h.region;
			if (!linkFrom) linkFrom = id;
			else if (linkFrom === id) linkFrom = null;
			else {
				edit.onlink?.(linkFrom, id);
				linkFrom = null;
			}
			return;
		}
		keyRegion = null;
		onpick?.(h.region, h.village);
	}
	function down(event: PointerEvent) {
		if (edit?.mode !== 'move') return;
		const [x, y] = local(event);
		const id = nearestRegion(x, y, 16);
		if (!id) return;
		canvas.setPointerCapture(event.pointerId);
		drag = { region: id, x, y };
	}
	function move(event: PointerEvent) {
		const [x, y] = local(event);
		if (drag) drag = { ...drag, x, y };
		else if (edit?.mode === 'link') pointer = [x, y];
		else onhover?.(hit(event));
	}
	function up() {
		const L = layout;
		if (!drag || !L) return;
		const { region, x, y } = drag;
		drag = null;
		edit?.onmove?.(region, ...L.inv(x, y));
	}
	function key(event: KeyboardEvent) {
		const L = layout;
		if (!L) return;
		const from = keyRegion ?? selected ?? regions[0]?.id;
		if (!from) return;
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			const v = villages.find((x) => x.region === from);
			if (v) onpick?.(from, v.id);
			keyRegion = null;
			return;
		}
		const dir = ({ ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] } as Record<string, [number, number]>)[event.key];
		if (!dir) return;
		event.preventDefault();
		const here = regions.find((r) => r.id === from);
		if (!here) return;
		let best: string | null = null, score = -Infinity;
		const candidates = here.neighbours?.length ? here.neighbours : regions.map((r) => r.id);
		for (const id of candidates) {
			const o = regions.find((r) => r.id === id);
			if (!o || o.id === from) continue;
			const dx = o.position[0] - here.position[0], dy = o.position[1] - here.position[1], len = Math.hypot(dx, dy) || 1;
			const s = (dx * dir[0] + dy * dir[1]) / len - len / 1e4;
			if (s > 0.3 && s > score) [best, score] = [o.id, s];
		}
		if (best) keyRegion = best;
	}

	onMount(() => {
		const ro = new ResizeObserver(() => schedule());
		ro.observe(stage);
		return () => {
			ro.disconnect();
			cancelAnimationFrame(pending);
			cancelAnimationFrame(waveFrame);
		};
	});
	// Geometrie se přepočítá při změně světa nebo přiblížení…
	$effect(() => {
		void regions;
		void villages;
		void focus;
		void relief;
		schedule();
	});
	// …kreslení při změně čehokoli, co obrazovka dodává.
	$effect(() => {
		void [layout, fill, fillAlpha, regionFill, hatch, regionHatch, edge, highlight, selected, labels, markers, arrows, keyRegion, edit, drag, linkFrom, pointer];
		render();
	});
</script>

<!-- Mapa je ovládaná klávesnicí (šipky, Enter), proto má tabindex a obsluhu kláves. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div
	class="map"
	bind:this={stage}
	role="application"
	tabindex="0"
	aria-label={label}
	aria-describedby={summary ? `${uid}-summary` : undefined}
	onkeydown={key}
>
	<canvas
		bind:this={canvas}
		class={edit?.mode ?? 'select'}
		onclick={click}
		onpointerdown={down}
		onpointermove={move}
		onpointerup={up}
		onmouseleave={() => {
			pointer = null;
			onhover?.(null);
		}}
	></canvas>
	{#if summary}<p id="{uid}-summary" class="sr">{summary}</p>{/if}
</div>

<style>
	.map {
		position: absolute;
		inset: 0;
	}
	canvas {
		display: block;
		cursor: pointer;
		touch-action: none;
	}
	canvas.add {
		cursor: crosshair;
	}
	canvas.move {
		cursor: grab;
	}
	canvas.move:active {
		cursor: grabbing;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
