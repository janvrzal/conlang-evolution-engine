// Pohyb v design systému: stejné křivky a délky jako tokeny v tokens.css (--e-*, --t-*).
// Zásady: čas teče zleva doprava, změna stavu jde po křivce S, odchod se zúží (nevybledne),
// šíření má zdroj, nic se nehýbe bez důvodu. Při omezeném pohybu je všechno hned v konečném stavu.
import { cubicOut } from "svelte/easing";
import { prefersReducedMotion } from "svelte/motion";
import type { TransitionConfig } from "svelte/transition";

/** délky v ms (zrcadlí --t-tick … --t-epoch) */
export const T = {
  tick: 90,
  snap: 160,
  unfold: 280,
  flow: 600,
  epoch: 1200,
} as const;

function bezier(x1: number, y1: number, x2: number, y2: number) {
  const cx = 3 * x1,
    bx = 3 * (x2 - x1) - cx,
    ax = 1 - cx - bx;
  const cy = 3 * y1,
    by = 3 * (y2 - y1) - cy,
    ay = 1 - cy - by;
  const x = (s: number) => ((ax * s + bx) * s + cx) * s;
  const dx = (s: number) => (3 * ax * s + 2 * bx) * s + cx;
  return (t: number) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let s = t;
    for (let i = 0; i < 6; i++) {
      const d = dx(s);
      if (Math.abs(d) < 1e-6) break;
      s -= (x(s) - t) / d;
    }
    s = Math.min(1, Math.max(0, s));
    return ((ay * s + by) * s + cy) * s;
  };
}
/** změna stavu, přesun: křivka S (--e-change) */
export const change = bezier(0.65, 0, 0.35, 1);
/** příchod, rozvinutí (--e-arrive) */
export const arrive = bezier(0.16, 1, 0.3, 1);
/** odchod, zúžení (--e-leave) */
export const leave = bezier(0.32, 0, 0.67, 0);
export { cubicOut };

/** true, když si uživatel přeje omezený pohyb */
export const still = () => prefersReducedMotion.current;
const dur = (ms: number) => (still() ? 0 : ms);

/** Rozvinutí bloku: výška od nuly po křivce S a obsah se odkryje zleva doprava.
 *  Jako odchod (out:) se blok zúží na nulovou výšku. */
export function unfold(
  node: HTMLElement,
  _params?: unknown,
  options?: { direction?: "in" | "out" | "both" },
): TransitionConfig {
  const h = node.offsetHeight;
  const cs = getComputedStyle(node);
  const pt = parseFloat(cs.paddingTop),
    pb = parseFloat(cs.paddingBottom),
    mt = parseFloat(cs.marginTop),
    mb = parseFloat(cs.marginBottom);
  const bt = parseFloat(cs.borderTopWidth),
    bb = parseFloat(cs.borderBottomWidth);
  const box = (g: number) =>
    `overflow:hidden;height:${g * h}px;padding-top:${g * pt}px;padding-bottom:${g * pb}px;margin-top:${g * mt}px;margin-bottom:${g * mb}px;border-top-width:${g * bt}px;border-bottom-width:${g * bb}px;`;
  if (options?.direction === "out")
    return { duration: dur(T.unfold), easing: leave, css: (t) => box(t) };
  // výška doběhne za --t-unfold, odkrytí zleva doprava za --t-flow
  const k = T.flow / T.unfold;
  return {
    duration: dur(T.flow),
    css: (t) =>
      `${box(change(Math.min(1, t * k)))}clip-path:inset(0 ${(1 - arrive(t)) * 100}% 0 0)`,
  };
}

/** Zúžení: odchod do tenké čáry uprostřed (vymření). Pro plovoucí prvky (oznámení, panel). */
export function narrow(
  _node: Element,
  { duration = T.snap }: { duration?: number } = {},
): TransitionConfig {
  return {
    duration: dur(duration),
    easing: leave,
    css: (t) => `clip-path:inset(${(1 - t) * 50}% 0 ${(1 - t) * 50}% 0)`,
  };
}

/** Výhonek: plovoucí prvek se odkryje zleva doprava (oznámení). */
export function sprout(
  _node: Element,
  { duration = T.flow }: { duration?: number } = {},
): TransitionConfig {
  return {
    duration: dur(duration),
    easing: arrive,
    css: (t) => `clip-path:inset(0 ${(1 - t) * 100}% 0 0)`,
  };
}

/** Rozevření od kotvy: panel nad prvkem vyroste odspodu nahoru (vyskakovací panel). */
export function rise(
  _node: Element,
  { duration = T.unfold }: { duration?: number } = {},
): TransitionConfig {
  return {
    duration: dur(duration),
    easing: arrive,
    css: (t) =>
      `clip-path:inset(${(1 - t) * 100}% 0 0 0);transform:translateY(${(1 - t) * 6}px)`,
  };
}

/** Posuvná podtržítková značka pod vybranou položkou (přepínač, karty).
 *  Akce si sama vytvoří značku; `key` je hodnota, při jejíž změně se značka přesune. */
export function underline(
  root: HTMLElement,
  params: { selector: string; key: unknown; thickness?: number },
) {
  let p = params;
  // značku vykreslí komponenta (<span data-underline>), aby ji Svelte při překreslení seznamu nesmazal
  const bar =
    root.querySelector<HTMLElement>(":scope > [data-underline]") ??
    root.appendChild(document.createElement("span"));
  Object.assign(bar.style, {
    position: "absolute",
    left: "0",
    top: "0",
    height: `${p.thickness ?? 2}px`,
    width: "0",
    background: "var(--ink)",
    pointerEvents: "none",
    transition: "none",
  });
  if (getComputedStyle(root).position === "static")
    root.style.position = "relative";
  root.appendChild(bar);
  let placed = false;
  const place = () => {
    const el = root.querySelector<HTMLElement>(p.selector);
    if (!el) {
      bar.style.width = "0";
      return;
    }
    const th = p.thickness ?? 2;
    bar.style.transition = placed
      ? "transform var(--t-snap) var(--e-change), width var(--t-snap) var(--e-change)"
      : "none";
    bar.style.width = `${el.offsetWidth}px`;
    bar.style.height = `${th}px`;
    bar.style.transform = `translate(${el.offsetLeft}px, ${el.offsetTop + el.offsetHeight - th}px)`;
    placed = true;
  };
  const ro = new ResizeObserver(() => {
    placed = false;
    place();
  });
  ro.observe(root);
  requestAnimationFrame(place);
  return {
    update(next: typeof params) {
      p = next;
      requestAnimationFrame(place);
    },
    destroy() {
      ro.disconnect();
    },
  };
}

/** Přechod mezi obrazovkami (SvelteKit onNavigate): nová obrazovka se odkryje zleva doprava přes starou.
 *  Lišta a pata stojí. Bez podpory View Transitions nebo při omezeném pohybu se přepne hned. */
export function screenTransition(navigation: { from: { url: URL } | null; to: { url: URL } | null; complete: Promise<void> }) {
	const doc = document as Document & { startViewTransition?: (cb: () => Promise<void>) => unknown };
	if (!doc.startViewTransition || still()) return;
	if (!navigation.from || !navigation.to || navigation.from.url.pathname === navigation.to.url.pathname) return;
	return new Promise<void>((resolve) => {
		doc.startViewTransition!(async () => {
			resolve();
			await navigation.complete;
		});
	});
}
