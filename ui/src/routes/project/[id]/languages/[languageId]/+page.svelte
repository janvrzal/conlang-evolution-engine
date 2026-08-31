<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { ArrowLeft, BookOpen, CalendarDays, GitBranch, History, Plus, Save, Users } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Select } from '$lib/components/ui/select';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import LanguageLexicon, { type LanguageWord } from '$lib/LanguageLexicon.svelte';
	import { fetchLanguage, fetchRunExport, fetchWordTrace } from '$lib/api';
	import { loadProject, projectState, scheduleSave } from '$lib/state.svelte';

	type AuthorEvent = { id: string; year: number; type: string; note: string; varietyId?: string };
	type AuditEvent = Record<string, unknown> & { kind?: string; year?: number; language_id?: string };

	let ready = $state(false);
	let selectedYear = $state(0);
	let selectedYearOption = $state('0');
	let words = $state<LanguageWord[]>([]);
	let auditEvents = $state<AuditEvent[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let labelDraft = $state('');
	let eventType = $state('metadata');
	let eventNote = $state('');
	let selectedTrace = $state<{ word: LanguageWord; steps: any[] } | null>(null);

	const languageId = $derived($page.params.languageId);
	const projectId = $derived($page.params.id);
	const years = $derived([...projectState.timeSteps].sort((a, b) => a - b));
	const activeSnapshot = $derived.by(() => {
		const year = [...years].filter((item) => item <= selectedYear).at(-1) ?? years[0] ?? 0;
		return projectState.snapshots[year] ?? { nodes: [], edges: [] };
	});
	const languageNode = $derived(activeSnapshot.nodes.find((node: any) => node.id === languageId) ?? null);
	const languageData = $derived((languageNode?.data ?? {}) as Record<string, any>);
	const authorEvents = $derived((languageData.languageEvents ?? []) as AuthorEvent[]);
	const visibleEvents = $derived([
		...auditEvents.filter((event) => Number(event.year ?? 0) <= selectedYear),
		...authorEvents.filter((event) => event.year <= selectedYear).map((event) => ({ ...event, kind: `author:${event.type}` }))
	].sort((left, right) => Number(right.year ?? 0) - Number(left.year ?? 0)) as AuditEvent[]);
	const varieties = $derived.by(() => {
		const configured = Array.isArray(languageData.communities) ? languageData.communities : [];
		const fromAudit = auditEvents
			.filter((event) => event.kind === 'variety_divergence' || event.kind === 'language_split_candidate')
			.map((event) => ({ id: String(event.variety_id ?? event.community_id), divergence: event.divergence, candidate: event.kind === 'language_split_candidate' }));
		return [...configured.map((item: any) => ({ id: item.variety_id ?? item.id, ...item })), ...fromAudit]
			.filter((item, index, all) => item.id && all.findIndex((candidate) => candidate.id === item.id) === index);
	});
	const catalog = $derived.by(() => {
		const known: Map<string, { id: string; label: string; year: number }> = new Map();
		for (const year of years) for (const node of projectState.snapshots[year]?.nodes ?? []) {
			if (!known.has(node.id)) known.set(node.id, { id: node.id, label: node.data?.label ?? node.id, year });
		}
		return [...known.values()].sort((left, right) => left.year - right.year || left.label.localeCompare(right.label));
	});

	onMount(() => {
		void (async () => {
			await loadProject(projectId ?? 'default');
			selectedYear = Number($page.url.searchParams.get('year') ?? projectState.timeSteps.at(-1) ?? 0);
			selectedYearOption = String(selectedYear);
			labelDraft = String(languageData.label ?? languageId);
			ready = true;
			await loadHistoricalState();
		})();
	});

	$effect(() => {
		if (!ready) return;
		labelDraft = String(languageData.label ?? languageId);
		void loadHistoricalState();
	});

	function setYear(value: string) {
		selectedYear = Number(value);
		selectedYearOption = value;
	}

	async function loadHistoricalState() {
		if (!projectState.simulationRunId) { words = []; auditEvents = []; return; }
		loading = true; error = null;
		try {
			words = await fetchLanguage(projectState.simulationRunId, languageId ?? '', selectedYear);
			const exported = await fetchRunExport(projectState.simulationRunId);
			auditEvents = (exported.events ?? []).filter((event: AuditEvent) => event.language_id === languageId);
		} catch (cause) { error = cause instanceof Error ? cause.message : String(cause); }
		finally { loading = false; }
	}

	function updateLanguageData(update: Record<string, unknown>) {
		projectState.snapshots = Object.fromEntries(Object.entries(projectState.snapshots).map(([year, snapshot]) => {
			if (Number(year) < selectedYear) return [year, snapshot];
			return [year, { ...snapshot, nodes: snapshot.nodes.map((node: any) => node.id === languageId ? { ...node, data: { ...node.data, ...update } } : node) }];
		}));
		scheduleSave();
	}

	function saveName() { updateLanguageData({ label: labelDraft }); addAuthorEvent('metadata', `Název jazyka: ${labelDraft}`); }
	function addAuthorEvent(type = eventType, note = eventNote, varietyId?: string) {
		const item: AuthorEvent = { id: `language-event-${Date.now()}`, year: selectedYear, type, note: note || type, varietyId };
		updateLanguageData({ languageEvents: [...authorEvents, item] });
		eventNote = '';
	}
	function decideVariety(varietyId: string, action: string) {
		if (action === 'split') {
			spawnLanguageFromVariety(varietyId);
			return;
		}
		const communities = (Array.isArray(languageData.communities) ? languageData.communities : []).map((item: any) =>
			(item.variety_id ?? item.id) === varietyId ? { ...item, status: action } : item
		);
		updateLanguageData({ communities });
		addAuthorEvent(`variety:${action}`, `Rozhodnutí pro varietu ${varietyId}: ${action}`, varietyId);
	}
	function spawnLanguageFromVariety(varietyId: string) {
		if (!languageNode) return;
		const newId = `lang-${Date.now()}`;
		const label = `${String(languageData.label ?? languageId)} — ${varietyId}`;
		projectState.snapshots = Object.fromEntries(Object.entries(projectState.snapshots).map(([year, snapshot]) => {
			if (Number(year) < selectedYear) return [year, snapshot];
			if (snapshot.nodes.some((node: any) => node.id === newId)) return [year, snapshot];
			const child = {
				...languageNode,
				id: newId,
				position: { x: Number(languageNode.position?.x ?? 0) + 230, y: Number(languageNode.position?.y ?? 0) + 130 },
				data: { ...languageData, label, year: selectedYear, isProto: false, originVariety: varietyId, languageEvents: [] }
			};
			const edge = { id: `inheritance-${languageId}-${newId}`, source: languageId, target: newId, type: 'inheritance', data: { kind: 'inheritance', year: selectedYear } };
			return [year, { ...snapshot, nodes: [...snapshot.nodes, child], edges: [...snapshot.edges, edge] }];
		}));
		addAuthorEvent('variety:split', `Vznikl nový jazyk ${label} z variety ${varietyId}.`, varietyId);
		scheduleSave();
	}
	async function showTrace(word: LanguageWord) {
		if (!projectState.simulationRunId) return;
		selectedTrace = { word, steps: await fetchWordTrace(projectState.simulationRunId, word.id) };
	}
</script>

<main class="min-h-screen bg-muted/30">
	<div class="mx-auto max-w-[1600px] space-y-6 p-4 md:p-8">
		<header class="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
			<div class="space-y-2"><Button href={`/project/${projectId}/map`} variant="ghost" size="sm"><ArrowLeft /> Na mapu</Button><div class="flex items-center gap-3"><div class="rounded-lg bg-primary/10 p-3 text-primary"><BookOpen size={24} /></div><div><p class="text-sm text-muted-foreground">Správa jazyka</p><h1 class="text-3xl font-semibold tracking-tight">{languageData.label ?? languageId}</h1><p class="text-sm text-muted-foreground">Stav v roce {selectedYear} · {words.length} živých lexémů</p></div></div></div>
			<div class="flex items-center gap-2"><CalendarDays size={17} class="text-muted-foreground" /><Select class="w-40" value={selectedYearOption} onchange={(event) => setYear(event.currentTarget.value)}>{#each years as year}<option value={String(year)}>{year}. rok</option>{/each}</Select></div>
		</header>

		{#if !languageNode}<Card><CardContent class="p-8 text-muted-foreground">Jazyk v tomto roce ještě neexistuje. Zvol dřívější rok nebo se vrať na mapu.</CardContent></Card>
		{:else}
			<div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
				<div class="space-y-6">
					{#if error}<Card class="border-destructive"><CardContent class="p-4 text-destructive">{error}</CardContent></Card>{/if}
					{#if loading}<Card><CardContent class="p-8 text-muted-foreground">Načítám historický stav jazyka…</CardContent></Card>{:else}<LanguageLexicon {words} onTrace={showTrace} />{/if}
					{#if selectedTrace}<Card><CardHeader><CardTitle>Historie: {selectedTrace.word.to}</CardTitle><CardDescription>{selectedTrace.word.concept_id}</CardDescription></CardHeader><CardContent><ol class="space-y-2">{#each selectedTrace.steps as step}<li class="flex gap-3 border-b pb-2 last:border-0"><span class="w-14 text-muted-foreground">{step.year}</span><strong>{step.form}</strong><span class="text-muted-foreground">{step.rule_name ?? step.note ?? step.type ?? ''}</span></li>{/each}</ol></CardContent></Card>{/if}
					<Card><CardHeader><CardTitle class="flex items-center gap-2"><History size={18} /> Události jazyka</CardTitle><CardDescription>Audit simulace a vlastní rozhodnutí autora pro vybraný rok.</CardDescription></CardHeader><CardContent class="space-y-3">{#each visibleEvents as event, index (`${event.kind}-${event.year}-${index}`)}<div class="rounded-lg border p-3"><div class="flex justify-between gap-3"><strong class="text-sm">{String(event.kind ?? event.type)}</strong><span class="text-xs text-muted-foreground">{event.year}</span></div><p class="mt-1 text-sm text-muted-foreground">{String(event.note ?? event.reason ?? event.rule ?? event.change_id ?? 'Historická událost')}</p></div>{:else}<p class="text-sm text-muted-foreground">Pro tento jazyk zatím nejsou žádné události.</p>{/each}</CardContent></Card>
				</div>
				<aside class="space-y-6 xl:sticky xl:top-6 xl:self-start">
					<Card><CardHeader><CardTitle>Metadata v roce {selectedYear}</CardTitle><CardDescription>Změna se uloží do tohoto a následujících snímků časové osy.</CardDescription></CardHeader><CardContent class="space-y-3"><Label>Název<Input bind:value={labelDraft} /></Label><Button class="w-full" onclick={saveName}><Save /> Uložit název</Button><Label>Populace<Input type="number" value={languageData.population?.size ?? ''} oninput={(event) => updateLanguageData({ population: { ...(languageData.population ?? {}), size: Number(event.currentTarget.value) } })} /></Label><Label>Počet center<Select value={String(languageData.population?.centers ?? 1)} onchange={(event) => updateLanguageData({ population: { ...(languageData.population ?? {}), centers: Number(event.currentTarget.value) } })}><option value="1">1 — centralizovaná</option><option value="2">2</option><option value="3">3</option><option value="5">5+</option></Select></Label></CardContent></Card>
					<Card><CardHeader><CardTitle class="flex items-center gap-2"><GitBranch size={18} /> Variety a dialekty</CardTitle><CardDescription>Výsledek sám nemění strom jazyků; rozhodnutí je vždy autorovo.</CardDescription></CardHeader><CardContent class="space-y-3">{#each varieties as variety}<div class="rounded-lg border p-3"><strong>{variety.id}</strong><p class="text-xs text-muted-foreground">{variety.divergence !== undefined ? `Divergence ${Math.round(Number(variety.divergence) * 100)} %` : variety.kind ?? 'komunita'}</p><div class="mt-2 flex flex-wrap gap-1"><Button size="xs" variant="outline" onclick={() => decideVariety(variety.id, 'assimilate')}>Asimilovat</Button><Button size="xs" variant="outline" onclick={() => decideVariety(variety.id, 'stabilize')}>Dialekt</Button><Button size="xs" onclick={() => decideVariety(variety.id, 'split')}>Nový jazyk</Button></div></div>{:else}<p class="text-sm text-muted-foreground">Přidej regionální či sociální komunity v nastavení jazyka; simulace pak sleduje jejich divergence.</p>{/each}</CardContent></Card>
					<Card><CardHeader><CardTitle>Přidat autorskou událost</CardTitle></CardHeader><CardContent class="space-y-3"><Select bind:value={eventType}><option value="metadata">Změna metadat</option><option value="variety:assimilate">Asimilace variety</option><option value="variety:split">Odštěpení variety</option><option value="institution">Institucionální změna</option><option value="migration">Migrace</option></Select><Input bind:value={eventNote} placeholder="Poznámka a historický důvod" /><Button class="w-full" variant="secondary" onclick={() => addAuthorEvent()}><Plus /> Přidat na osu</Button></CardContent></Card>
					<Card><CardHeader><CardTitle class="flex items-center gap-2"><Users size={18} /> Databáze jazyků</CardTitle></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>Jazyk</TableHead><TableHead>Od</TableHead></TableRow></TableHeader><TableBody>{#each catalog as item}<TableRow><TableCell><a class="text-primary hover:underline" href={`/project/${projectId}/languages/${item.id}?year=${selectedYear}`}>{item.label}</a></TableCell><TableCell>{item.year}</TableCell></TableRow>{/each}</TableBody></Table></CardContent></Card>
				</aside>
			</div>
		{/if}
	</div>
</main>
