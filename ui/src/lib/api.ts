/**
 * Zjištění adresy CEE API.
 *
 * Backend si port volí sám (viz `cee ui`), protože 8000 běžně obsadí jiná
 * lokální aplikace. Adresu proto neurčujeme natvrdo, ale ve dvou krocích:
 *
 *  1. `VITE_CEE_API_URL` — zapsané příkazem `cee ui` do `ui/.env.local`.
 *  2. Když proměnná chybí nebo na ní nikdo neodpovídá, prohledáme stejný
 *     rozsah portů, ze kterého vybírá backend.
 *
 * Na portu může sedět cizí aplikace, která na `/api/health` taky odpoví 200,
 * proto se ověřuje podpis `engine`.
 */

const ENGINE_SIGNATURE = 'Conlang Evolution Engine';
const DEFAULT_PORT = 8000;
const SCAN_RANGE = 20;
const PROBE_TIMEOUT_MS = 700;

let cachedBase: string | null = null;

async function isCeeApi(base: string): Promise<boolean> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
	try {
		const res = await fetch(`${base}/api/health`, { signal: controller.signal });
		if (!res.ok) return false;
		const data = await res.json();
		return data?.engine === ENGINE_SIGNATURE;
	} catch {
		// Odmítnuté spojení, timeout, chybějící CORS hlavičky nebo jiný obsah —
		// všechno znamená „tady CEE neběží".
		return false;
	} finally {
		clearTimeout(timer);
	}
}

/** Vrátí základní adresu API, nebo vyhodí chybu s návodem, když server neběží. */
export async function resolveApiBase(): Promise<string> {
	if (cachedBase) return cachedBase;

	const configured = import.meta.env.VITE_CEE_API_URL;
	if (configured && (await isCeeApi(configured))) {
		cachedBase = configured;
		return cachedBase;
	}

	const candidates = Array.from(
		{ length: SCAN_RANGE + 1 },
		(_, i) => `http://127.0.0.1:${DEFAULT_PORT + i}`
	);

	const found = await Promise.all(
		candidates.map(async (base) => ((await isCeeApi(base)) ? base : null))
	);

	// Nejnižší nalezený port, ať je výsledek stabilní napříč běhy.
	const match = found.find((base): base is string => base !== null);
	if (!match) {
		throw new Error(
			`CEE API nebylo nalezeno na portech ${DEFAULT_PORT}–${DEFAULT_PORT + SCAN_RANGE}. ` +
				`Spusť backend příkazem: cee ui`
		);
	}

	cachedBase = match;
	return cachedBase;
}

/** Zapomene nalezenou adresu — použij po restartu backendu na jiném portu. */
export function resetApiBase(): void {
	cachedBase = null;
}

export async function simulate(payload: Record<string, unknown>) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/simulate`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	if (!res.ok) {
		throw new Error(`API vrátilo ${res.status} ${res.statusText}`);
	}
	return res.json();
}
