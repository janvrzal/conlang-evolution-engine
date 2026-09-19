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

/**
 * Revize backendu, kterou tenhle frontend potřebuje (viz cee/api/ports.py).
 * Běží-li starší, chybí mu endpointy a odpovídal by holým 404 — což vypadá
 * jako chyba aplikace, přestože stačí restartovat `cee ui`.
 */
const REQUIRED_API_REVISION = 5;
const DEFAULT_PORT = 8000;
const SCAN_RANGE = 20;
const PROBE_TIMEOUT_MS = 700;

let cachedBase: string | null = null;
let foundRevision = 0;

class StaleBackendError extends Error {
	constructor(revision: number) {
		super(
			`Backend běží ve starší verzi (rev ${revision}, potřeba ${REQUIRED_API_REVISION}). ` +
				`Ukonči běžící 'cee ui' a spusť ho znovu.`
		);
		this.name = 'StaleBackendError';
	}
}

/** Ověří, že nalezený backend umí, co frontend potřebuje. */
function assertFreshEnough(): void {
	if (foundRevision < REQUIRED_API_REVISION) {
		cachedBase = null;
		throw new StaleBackendError(foundRevision);
	}
}

async function isCeeApi(base: string): Promise<boolean> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
	try {
		const res = await fetch(`${base}/api/health`, { signal: controller.signal });
		if (!res.ok) return false;
		const data = await res.json();
		if (data?.engine !== ENGINE_SIGNATURE) return false;

		foundRevision = typeof data.api_revision === 'number' ? data.api_revision : 0;
		return true;
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
		assertFreshEnough();
		cachedBase = configured;
		return configured;
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

	assertFreshEnough();
	cachedBase = match;
	return match;
}

/** Zapomene nalezenou adresu — použij po restartu backendu na jiném portu. */
export { StaleBackendError };

export function resetApiBase(): void {
	cachedBase = null;
	foundRevision = 0;
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

export async function simulateDynamic(payload: Record<string, unknown>) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/simulate_dynamic`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	if (!res.ok) {
		throw new Error(`API vrátilo ${res.status} ${res.statusText}`);
	}
	return res.json();
}

export async function generateProtolangApi(payload: Record<string, unknown>) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/protolang/generate`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	if (!res.ok) {
		throw new Error(`API vrátilo ${res.status} ${res.statusText}`);
	}
	return res.json();
}

/** Vývoj jednoho jazyka v čase — epochy, zvukové změny a derivace slov. */
export async function evolveLanguage(payload: Record<string, unknown>) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/evolve`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	if (!res.ok) {
		throw new Error(`API vrátilo ${res.status} ${res.statusText}`);
	}
	return res.json();
}

// --- Projekty (persistence rozdělané práce) ----------------------------------

export type ProjectPayload = { name: string; data: Record<string, unknown> };

export async function fetchProject(id: string) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/projects/${encodeURIComponent(id)}`);

	// 404 není chyba — projekt se prostě ještě nezaložil.
	if (res.status === 404) return null;
	if (!res.ok) throw new Error(`Načtení projektu selhalo: ${res.status} ${res.statusText}`);

	const body = await res.json();
	return body.project as {
		id: string;
		name: string;
		updated_at: string;
		data: Record<string, unknown>;
	};
}

export async function saveProject(id: string, payload: ProjectPayload) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/projects/${encodeURIComponent(id)}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload)
	});

	if (!res.ok) throw new Error(`Uložení projektu selhalo: ${res.status} ${res.statusText}`);
	return (await res.json()).project;
}

export async function listProjects() {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/projects`);
	if (!res.ok) throw new Error(`Výpis projektů selhal: ${res.status}`);
	return (await res.json()).projects as { id: string; name: string; updated_at: string }[];
}

export async function deleteProject(id: string) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/projects/${encodeURIComponent(id)}`, {
		method: 'DELETE'
	});
	if (!res.ok) throw new Error(`Smazání projektu selhalo: ${res.status} ${res.statusText}`);
}

/** Přenese výslovně zvolený výsledek ze starší lokální Neo4j instalace. */
export async function importLegacyNeo4j(id: string) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/projects/${encodeURIComponent(id)}/import-legacy-neo4j`, {
		method: 'POST'
	});
	if (!res.ok) throw new Error(`Import starší simulace selhal: ${res.status}`);
	return res.json() as Promise<{ status: string; run_id: string; words: number }>;
}

/**
 * Převede název projektu na ID, které projde sítem na backendu
 * (písmena včetně diakritiky, číslice, pomlčka, podtržítko; nejvýše 64 znaků).
 */
export function slugify(name: string): string {
	const slug = name
		.trim()
		.toLowerCase()
		.replace(/\s+/g, '-')
		// Vše ostatní (tečky, lomítka, interpunkce) pryč — jinak backend
		// odpoví 400 a projekt nevznikne.
		.replace(/[^\p{L}\p{N}_-]/gu, '')
		.replace(/-{2,}/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 64);

	return slug;
}

export async function fetchLanguage(runId: string, nodeId: string, year?: number) {
	const base = await resolveApiBase();
	let url = `${base}/api/runs/${encodeURIComponent(runId)}/languages/${encodeURIComponent(nodeId)}`;
	if (year !== undefined) {
		url += `?year=${year}`;
	}
	const res = await fetch(url);
	if (!res.ok) throw new Error(`Načtení jazyka selhalo: ${res.status}`);
	const body = await res.json();
	if (body.status === 'error') throw new Error(body.error);
	return body.words;
}

export async function fetchWordTrace(runId: string, wordId: string) {
	const base = await resolveApiBase();
	const res = await fetch(
		`${base}/api/runs/${encodeURIComponent(runId)}/words/${encodeURIComponent(wordId)}/trace`
	);
	if (!res.ok) throw new Error(`Načtení historie slova selhalo: ${res.status}`);
	const body = await res.json();
	if (body.status === 'error') throw new Error(body.error);
	return body.trace;
}

export async function fetchIsogloss(runId: string, conceptId: string, year?: number) {
	const base = await resolveApiBase();
	let url = `${base}/api/runs/${encodeURIComponent(runId)}/isogloss/${encodeURIComponent(conceptId)}`;
	if (year !== undefined) url += `?year=${year}`;
	const res = await fetch(url);
	if (!res.ok) throw new Error(`Načtení izoglosy selhalo: ${res.status}`);
	const body = await res.json();
	if (body.status === 'error') throw new Error(body.error);
	return body.isogloss;
}

/** Stáhne auditovatelný JSON export jedné simulace. */
export async function fetchRunExport(runId: string) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/runs/${encodeURIComponent(runId)}/export`);
	if (!res.ok) throw new Error(`Export selhal: ${res.status} ${res.statusText}`);
	return res.json();
}

export type SchemaProfile = {
	id: string;
	label: string;
	description: string;
	kind: string;
	license: string;
	provenance: string;
};

export async function fetchSchemaProfiles(): Promise<SchemaProfile[]> {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/schema-profiles`);
	if (!res.ok) throw new Error(`Načtení profilů selhalo: ${res.status}`);
	return res.json();
}

export type PhoibleStatus = {
	available: boolean;
	repository_present: boolean;
	inventories?: number;
	revision?: string | null;
	error?: string;
};

export async function fetchPhoibleStatus(): Promise<PhoibleStatus> {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/phonology/status`);
	if (!res.ok) throw new Error(`Stav PHOIBLE nelze načíst: ${res.status}`);
	return res.json();
}

export async function updatePhoibleData(): Promise<PhoibleStatus> {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/phonology/update-data`, { method: 'POST' });
	if (!res.ok) throw new Error(`Aktualizace PHOIBLE selhala: ${res.status}`);
	return res.json();
}

export async function fetchRunMetrics(runId: string) {
	const base = await resolveApiBase();
	const res = await fetch(`${base}/api/runs/${encodeURIComponent(runId)}/metrics`);
	if (!res.ok) throw new Error(`Metriky nelze načíst: ${res.status}`);
	return (await res.json()).metrics;
}

export async function fetchGrammar(runId: string, nodeId: string): Promise<string> {
	const base = await resolveApiBase();
	const res = await fetch(
		`${base}/api/runs/${encodeURIComponent(runId)}/grammars/${encodeURIComponent(nodeId)}`
	);
	if (!res.ok) throw new Error(`Gramatiku nelze načíst: ${res.status}`);
	return (await res.json()).grammar_md;
}

export async function fetchEdgeRules(runId: string, childId: string) {
	const base = await resolveApiBase();
	const res = await fetch(
		`${base}/api/runs/${encodeURIComponent(runId)}/edges/${encodeURIComponent(childId)}/rules`
	);
	if (!res.ok) throw new Error(`Pravidla hrany nelze načíst: ${res.status}`);
	return (await res.json()).rules as {
		year: number;
		rule: string;
		schema_id: string;
		hit_count: number;
		deleted_segments: number;
	}[];
}
