<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import {
		SvelteFlow,
		Controls,
		Background,
		BackgroundVariant,
		ConnectionLineType,
		ConnectionMode,
		addEdge,
		type Node,
		type Edge
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	
	import LanguageNode from '$lib/LanguageNode.svelte';
	import ContactEdge from '$lib/ContactEdge.svelte';
	import LanguageDetail from '$lib/LanguageDetail.svelte';
	import TimelineControl from '$lib/TimelineControl.svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Select } from '$lib/components/ui/select';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Label } from '$lib/components/ui/label';
	import {
		MousePointer2,
		GitCommitHorizontal,
		ArrowLeftRight,
		X,
		Download,
		Trash2,
		Map
	} from 'lucide-svelte';
	
	import { simulateDynamic, resetApiBase, fetchIsogloss, fetchRunExport, importLegacyNeo4j } from '$lib/api';
	import { projectState, loadProject, scheduleSave, flushSave } from '$lib/state.svelte';
	import { propagateSnapshots, findEdgeBetween, retypeEdge, newEdgeFields, snapshotForCanvas } from '$lib/timeline';
	import type { TLEdge } from '$lib/timeline';
	import { onMount, untrack } from 'svelte';
	import { t } from '$lib/i18n.svelte';

	const nodeTypes = {
		language: LanguageNode
	};

	const edgeTypes = {
		contact: ContactEdge
	};

	// Obsidian kreslí spoje jako rovné čáry. Výchozí bezier se u uzlů nad sebou
	// zamotává do smyček, které nic neznamenají.
	//
	// `data.year` tu dřív odkazoval na `timeSteps`/`currentTimeIndex`, které
	// jsou v tomhle souboru deklarované až o desítky řádků níž (`let ... =
	// $state(...)`). V Svelte 5 runes se top-level `let` vyhodnocuje v pořadí
	// zápisu jako běžný JS blok, takže čtení proměnné před její deklarací
	// (temporal dead zone) shazovalo celou stránku hned při načtení.
	// `onConnect` navíc `data` pro každou novou hranu stejně nastavuje sám,
	// takže tenhle výchozí `year` byl navíc mrtvý kód.
	const defaultEdgeOptions = {
		type: 'straight',
		style: 'stroke: var(--edge-stroke, #6b6f76); stroke-width: 1.2; opacity: 0.55'
	};

	// Drill-down panel se otevírá vedle plátna, ne přes něj.
	let detailOpen = $state(false);

	// xyflow v1 nemá vestavěné mazání klávesou, takže si výběr hrany držíme sami.
	let selectedEdgeId = $state<string | null>(null);
	
	let activeIsogloss = $state<{ conceptId: string, data: Record<string, string> } | null>(null);

	// Zvýraznění vybrané hrany řeší CSS přes třídu .selected, kterou přidává
	// sám xyflow. Přepisovat kvůli tomu pole hran by rozbilo bind:edges.
	function onEdgeClick({ edge }: { edge: Edge }) {
		selectedEdgeId = edge.id;
		selectedNodeId = null;
		detailOpen = false;
	}

	function deleteSelectedEdge() {
		if (!selectedEdgeId) return;
		edges = edges.filter((e) => e.id !== selectedEdgeId);
		selectedEdgeId = null;
	}

	/** Pravý klik smaže hranu rovnou — bez oklik přes výběr. */
	function onEdgeContextMenu({ edge, event }: { edge: Edge; event: MouseEvent }) {
		event.preventDefault();
		edges = edges.filter((e) => e.id !== edge.id);
		if (selectedEdgeId === edge.id) selectedEdgeId = null;
	}

	function onKeyDown(event: KeyboardEvent) {
		if (event.key !== 'Delete' && event.key !== 'Backspace') return;

		// Ať se hrana nemaže, když uživatel píše do pole.
		const cil = event.target as HTMLElement | null;
		if (cil && ['INPUT', 'TEXTAREA'].includes(cil.tagName)) return;
		if (cil?.isContentEditable) return;

		if (selectedEdgeId) {
			event.preventDefault();
			deleteSelectedEdge();
		}
	}

	// --- Time Snapshot Logic ---
	// Osa i snapshoty žijí v projectState, protože se ukládají na disk.
	// Dokud byly lokální v komponentě, mizely při přechodu na Metaeditaci i po F5.
	let currentTimeIndex = $state(0);

	let timeSteps = $derived(projectState.timeSteps);
	let snapshots = $derived(projectState.snapshots);

	onMount(() => {
		// Protojazyk zakládá store, ne tenhle callback — jinak ho stihne přebít
		// synchronizační efekt níž a do projektu se uloží prázdný snapshot.
		void loadProject($page.params.id ?? 'default');

		const flush = () => void flushSave();
		window.addEventListener('beforeunload', flush);
		window.addEventListener('keydown', onKeyDown);
		return () => {
			window.removeEventListener('beforeunload', flush);
			window.removeEventListener('keydown', onKeyDown);
		};
	});

	// Každá změna uzlů, hran nebo osy naplánuje uložení.
	$effect(() => {
		JSON.stringify(projectState.snapshots);
		JSON.stringify(projectState.timeSteps);
		if (projectState.loaded) scheduleSave();
	});

	let nodes = $state<Node[]>([]);
	let edges = $state<Edge[]>([]);

	// Rok, ke kterému patří lokální `nodes` / `edges`.
	//
	// Bez téhle stopy byly oba efekty níž kruhové: první četl snapshoty a psal
	// do nodes, druhý četl nodes a psal do snapshotů. Při přepnutí roku se
	// stihl spustit ten druhý dřív — a zapsal uzly starého roku do nového,
	// čímž přepsal jeho obsah.
	let loadedYear = $state<number | null>(null);

	// 1) Načtení snapshotu — jen když se rok skutečně změnil.
	$effect(() => {
		if (!projectState.loaded) return;
		const year = timeSteps[currentTimeIndex];
		if (year === undefined || year === loadedYear) return;

		if (!projectState.snapshots[year]) {
			// Kaskáda zařídí naplnění
			projectState.snapshots[year] = { nodes: [], edges: [] };
			propagateTimeline();
		}

		// XYFlow dostává izolovanou kopii. Jeho interní bindování tak nemůže
		// při načítání jednoho roku omylem zmutovat perzistentní snapshot jiného.
		const canvasSnapshot = snapshotForCanvas(projectState.snapshots[year], year);
		nodes = canvasSnapshot.nodes as Node[];
		edges = canvasSnapshot.edges as Edge[];
		loadedYear = year;
	});

	// 2) Zápis zpět — jen do roku, ke kterému lokální stav opravdu patří.
	$effect(() => {
		if (!projectState.loaded || loadedYear === null) return;
		const snapshot = projectState.snapshots[loadedYear];
		if (!snapshot) return;

		snapshot.nodes = $state.snapshot(nodes);
		snapshot.edges = $state.snapshot(edges);

		// Zpropagovat změny do budoucnosti — jen z právě editovaného roku dál.
		// `propagateTimeline()` bez argumentu by přepočítal celou osu od nuly,
		// a "vezmi uzel ze staršího roku a přepiš jím stejné ID v novějším"
		// nerozlišuje "beze změny zděděné" od "právě ručně upraveného" —
		// jakákoli editace v pozdějším roce (přejmenování, tombstone, smazání
		// hrany) by se tou stejnou cascade, kterou zrovna spouští, vzápětí
		// vrátila zpět na starší hodnotu.
		propagateTimeline(loadedYear);
	});

	function propagateTimeline(fromYear?: number) {
		untrack(() => {
			const steps = projectState.timeSteps;
			if (steps.length < 2) return;

			// Logika kaskády (konverze dědičnost -> kontakt, mazání i tombstone
			// se promítají dopředu) žije v $lib/timeline.ts, aby šla otestovat
			// nezávisle na Svelte reaktivitě. Mutuje `projectState.snapshots`
			// na místě — nikdy nepřepisuje objekt roku, odkud se propaguje, jen
			// zapisuje do let PO něm. Kdyby se sem místo toho přiřazoval celý
			// nový strom, referenční změna u toho roku by znovu spustila
			// ukládací efekt výš, ten by znovu zavolal kaskádu — nekonečná smyčka.
			propagateSnapshots(projectState.snapshots, steps, fromYear ?? undefined);
		});
	}

	// --- Interaction Logic (Toolbar) ---
	// Hrana je buď dědičnost (rodič -> potomek), nebo kontakt (sousedé, kteří
	// se navzájem ovlivňují). Bez rozlišení se všechno bralo jako dědičnost
	// a propojené jazyky na sebe nikdy nepůsobily.
	let activeTool = $state<'interact' | 'relationship'>('interact');
	let relationshipType = $state<'inheritance' | 'contact'>('inheritance');

	/**
	 * Nová hrana dostane druh podle právě zvoleného nástroje.
	 *
	 * `addEdge()` z xyflow tiše zahodí spojení, pokud mezi stejnou dvojicí
	 * uzlů (na stejných handlech) už nějaká hrana existuje — kontroluje jen
	 * `source`/`target`, na `type` se vůbec nedívá. Bez ošetření tak
	 * přetažení "Kontaktu" nad uzly, které už spojuje dědičnost, nedělalo
	 * vůbec nic: stará dědičnost tam prostě zůstala ležet a vypadalo to,
	 * že se kontakt "nepřepnul". Zdroj a cíl v jednom roce mají smysl jen
	 * jako jeden vztah, takže existující hranu rovnou přetypujeme.
	 */
	function onConnect(connection: { source: string; target: string }) {
		const year = timeSteps[currentTimeIndex];
		const wantsContact = relationshipType === 'contact';

		const existingIdx = findEdgeBetween(edges as unknown as TLEdge[], connection.source, connection.target);
		if (existingIdx !== -1) {
			edges = edges.map((e, i) =>
				i === existingIdx ? (retypeEdge(e as unknown as TLEdge, wantsContact, year) as unknown as Edge) : e
			);
			return;
		}

		// Explicitní `id` ve stejném formátu jako generuje `addEdge()` samo —
		// bez něj TS spojuje objekt s "Edge" větví typu Connection | Edge
		// a stěžuje si na chybějící povinné `id`, i když by šlo o platné
		// nové spojení (addEdge() by si id doplnil sám).
		edges = addEdge(
			{ id: `xy-edge__${connection.source}-${connection.target}`, ...connection, ...newEdgeFields(wantsContact, year) },
			edges
		);
	}

	/**
	 * Tombstone: mrtvý jazyk už nikoho neovlivňuje.
	 *
	 * `propagateTimeline()` se stará jen o roky PO tomhle — kdykoli přepíše
	 * jen `nextSnapshot`, nikdy zpětně to, co právě editujeme. Zapnutí
	 * tombstone proto musí hrany aktuálního roku smazat rovnou tady, jinak
	 * by "odstraní všechny jeho edges" platilo až od dalšího roku a v
	 * aktuálním by uzel dál vypadal propojený.
	 */
	function setDead(nodeId: string, isDead: boolean) {
		nodes = nodes.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, isDead } } : n));
		if (isDead) {
			edges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
		}
	}

	// Selection
	let selectedNodeId = $state<string | null>(null);
	let selectedNodeData = $derived(nodes.find(n => n.id === selectedNodeId));

	// xyflow v1 (Svelte 5) předává handlery jako callback props, ne přes on:.
	// Direktiva `on:nodeclick` se nikdy nespustila, takže panel nešlo otevřít.
	function onNodeClick({ node }: { node: Node }) {
		selectedNodeId = node.id;
		detailOpen = true;
	}

	function onPaneClick() {
		selectedNodeId = null;
		selectedEdgeId = null;
		detailOpen = false;
	}

	function addLanguage() {
		const year = timeSteps[currentTimeIndex];
		const id = `lang-${Date.now()}`;
		const newNode = {
			id,
			type: 'language',
			position: { x: Math.random() * 300 + 200, y: Math.random() * 300 + 200 },
					data: { label: generateLanguageName(id), year }
		};
		nodes = [...nodes, newNode];
	}

	const nameStarts = ['Aru', 'Bela', 'Daro', 'Eli', 'Kara', 'Luma', 'Mori', 'Nava', 'Sora', 'Tavi'];
	const nameEnds = ['n', 'ra', 'li', 'ma', 'ta', 'vek', 'rin', 'sa', 'dor', 'ya'];

	function generateLanguageName(seed: string): string {
		let value = 0;
		for (let i = 0; i < seed.length; i += 1) value = (value * 31 + seed.charCodeAt(i)) >>> 0;
		return `${nameStarts[value % nameStarts.length]}${nameEnds[(value >>> 8) % nameEnds.length]}`;
	}

	function addTimeStep() {
		const input = prompt('Zadejte rok pro nový časový snapshot:', '');
		if (input === null) return;
		const year = parseInt(input, 10);
		if (!isNaN(year) && !timeSteps.includes(year)) {
			projectState.timeSteps = [...timeSteps, year].sort((a, b) => a - b);
			currentTimeIndex = projectState.timeSteps.indexOf(year);
		}
	}

	// Calculate proportional position for timeline points
	let maxYear = $derived(Math.max(...timeSteps, 1));

	// --- Simulation Logic ---
	let isLoading = $state(false);
	let errorMessage = $state('');
	let showResultsModal = $state(false);

	async function handleIsogloss(conceptId: string) {
		if (!projectState.simulationRunId) return;
		try {
			const data = await fetchIsogloss(projectState.simulationRunId, conceptId, timeSteps[currentTimeIndex]);
			activeIsogloss = { conceptId, data };
			updateNodesIsogloss();
		} catch (e) {
			console.error("Izoglosa failed", e);
		}
	}
	
	function clearIsogloss() {
		activeIsogloss = null;
		updateNodesIsogloss();
	}
	
	function updateNodesIsogloss() {
		nodes = nodes.map(n => {
			if (activeIsogloss) {
				return { ...n, data: { ...n.data, isoglossValue: activeIsogloss.data[n.id] || '-' } };
			} else {
				const { isoglossValue, ...rest } = n.data as any;
				return { ...n, data: rest };
			}
		});
	}

	async function exportSimulation() {
		if (!projectState.simulationRunId) return;
		try {
			const payload = await fetchRunExport(projectState.simulationRunId);
			const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `${$page.params.id}-${projectState.simulationRunId}.json`;
			link.click();
			URL.revokeObjectURL(url);
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : String(e);
		}
	}

	async function importPreviousSimulation() {
		isLoading = true;
		errorMessage = '';
		try {
			const result = await importLegacyNeo4j($page.params.id ?? 'default');
			projectState.simulationRunId = result.run_id;
			projectState.simulationRunAt = new Date().toISOString();
			await flushSave();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : String(e);
		} finally {
			isLoading = false;
		}
	}

	async function runSimulation() {
		if (projectState.generatedProtoLexicon.length === 0) {
			alert("Nejprve vygeneruj testovací slovník v sekci Metaeditace!");
			return;
		}
		
		isLoading = true;
		errorMessage = '';
		// Artificial minimum wait to show the progress bar if the API is too fast
		const minWait = new Promise(resolve => setTimeout(resolve, 800));
		
		try {
			// Backend musí dostat celou historii mapy. Dědičnost žije jen v
			// okamžiku odštěpení; v dalších snímcích se správně mění na kontakt.
			// Poslat jen aktuálně zobrazený snímek by proto genealogii zahodilo.
			const topology_data = {
				snapshots: timeSteps.map((year) => ({
					year,
					nodes: projectState.snapshots[year]?.nodes ?? [],
					edges: projectState.snapshots[year]?.edges ?? []
				}))
			};

			const data = await simulateDynamic({
				topology_data,
				proto_lexicon: projectState.generatedProtoLexicon,
				years: maxYear,
				run_id: projectState.simulationRunId
			});

			await minWait;

			if (data.status === 'success') {
				projectState.simulationRunAt = new Date().toISOString();
				projectState.simulationRunId = data.run_id;
				// Uložení je lokální ve výchozím stavu; Neo4j je jen volitelný adaptér.
				void flushSave();
				
				// Úspěšně nahráno do DB. Tady bychom případně mohli zobrazit toast notifikaci.
			} else {
				errorMessage = `Engine vrátil stav '${data.status}'.`;
			}
		} catch (e) {
			await minWait;
			resetApiBase();
			errorMessage = e instanceof Error ? e.message : String(e);
			console.error("Chyba při volání API", e);
		} finally {
			isLoading = false;
		}
	}
</script>

<svelte:head>
	<title>Mapa | Projekt {$page.params.id}</title>
</svelte:head>

<div class="relative w-full h-screen bg-background overflow-hidden flex tool-{activeTool}">
	<!-- Canvas -->
	<div class="absolute inset-0">
		<!--
			XYFlow si ke každému ID uzlu ukládá interní změřenou pozici. ID jsou
			záměrně stejná ve všech časových snímcích, ale jejich `position` se
			mění. Bez nového mountu si knihovna občas nechala staré kotvy hran:
			uzel už byl napravo, zatímco čára končila v jeho pozici z minulého
			roku. Klíč podle načteného roku proto obnoví jen interní geometrii;
			data nadále zůstávají v `projectState.snapshots`.
		-->
		{#key loadedYear}
			<SvelteFlow
				bind:nodes
				bind:edges
				{nodeTypes}
				{edgeTypes}
				onedgeclick={onEdgeClick}
				onedgecontextmenu={onEdgeContextMenu}
				{defaultEdgeOptions}
				connectionLineType={ConnectionLineType.Straight}
				connectionMode={ConnectionMode.Loose}
				nodesDraggable={activeTool === 'interact'}
				nodesConnectable={activeTool === 'relationship'}
				onconnect={onConnect}
				elementsSelectable={true}
				onnodeclick={onNodeClick}
				onpaneclick={onPaneClick}
				fitView
			>
				<Background variant={BackgroundVariant.Dots} gap={28} size={1} class="opacity-30" />
				<Controls class="bg-card border-border fill-foreground" />
			</SvelteFlow>
		{/key}
	</div>

	<!-- Toolbar Panel -->
	<div class="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex bg-card rounded-md border shadow-sm p-1 gap-1">
		<Button 
			variant={activeTool === 'interact' ? 'default' : 'ghost'}
			size="sm" 
			class="px-3"
			onclick={() => activeTool = 'interact'}
			title={t('moveHint')}
		>
			<MousePointer2 class="w-4 h-4 mr-2" />
			{t('interaction')}
		</Button>
		<Button 
			variant={activeTool === 'relationship' ? 'default' : 'ghost'}
			size="sm" 
			class="px-3"
			onclick={() => activeTool = 'relationship'}
			title={t('relationshipHint')}
		>
			<GitCommitHorizontal class="w-4 h-4 mr-2" />
			{t('relationship')}
		</Button>
		{#if activeTool === 'relationship'}
			<Select class="h-8 w-36" bind:value={relationshipType} title={t('relationship')}>
				<option value="inheritance">{t('inheritance')}</option>
				<option value="contact">{t('contact')}</option>
			</Select>
		{/if}
		{#if selectedEdgeId}
			<div class="w-px bg-border mx-1"></div>
			<Button
				variant="ghost"
				size="sm"
				class="px-3 text-destructive hover:text-destructive"
				onclick={deleteSelectedEdge}
				title="Smazat vybrané spojení (Delete)"
			>
				<Trash2 class="w-4 h-4 mr-2" />
				Smazat spojení
			</Button>
		{/if}
	</div>

	<!-- Izoglosa Banner -->
	{#if activeIsogloss}
		<div class="absolute top-4 left-1/2 ml-[220px] z-10 flex bg-primary text-primary-foreground rounded-md shadow-lg p-1.5 px-3 items-center gap-2 animate-in slide-in-from-top-4">
			<Map class="w-4 h-4" />
			<span class="text-sm font-semibold tracking-tight">Izoglosa: {activeIsogloss.conceptId}</span>
			<button class="ml-2 hover:bg-primary-foreground/20 p-0.5 rounded transition-colors" onclick={clearIsogloss}>
				<X size={16} />
			</button>
		</div>
	{/if}

	<!-- Left Panel: Project Settings -->
	<div class="absolute top-4 left-4 z-10 w-80 flex flex-col gap-4">
		<Card class="shadow-sm">
			<CardHeader class="pb-3">
				<CardTitle class="text-lg">Projekt: {projectState.name}</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<Button class="w-full" variant="outline" size="sm" onclick={addLanguage}>
					+ {t('addNode')}
				</Button>
				<Button class="w-full" variant="outline" size="sm" onclick={() => goto(`/project/${$page.params.id}/meta`)}>
					{t('projectSettings')}
				</Button>
				<Button class="w-full relative overflow-hidden" variant="default" size="sm" onclick={runSimulation} disabled={isLoading}>
					<span class="relative z-10">{isLoading ? '…' : t('simulate')}</span>
					{#if isLoading}
						<div class="absolute bottom-0 left-0 h-1 bg-white/40 animate-pulse transition-all duration-[800ms] ease-out w-full" style="animation: fillProgress 800ms ease-out forwards;"></div>
					{/if}
				</Button>
				{#if projectState.simulationRunId}
					<Button class="w-full" variant="outline" size="sm" onclick={exportSimulation}>
						<Download class="w-4 h-4 mr-2" /> Exportovat simulaci
					</Button>
				{:else}
					<Button class="w-full" variant="outline" size="sm" onclick={importPreviousSimulation} disabled={isLoading}>
						{t('importLegacy')}
					</Button>
				{/if}
				{#if errorMessage}
					<p class="text-xs text-destructive">{errorMessage}</p>
				{/if}

				<div class="text-xs text-muted-foreground space-y-1">
					<p>{t('currentStep')}: <strong>{t('year')} {timeSteps[currentTimeIndex]}</strong></p>
					<p class="flex items-center gap-1.5">
						{#if projectState.status === 'saving'}
							<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Ukládám…
						{:else if projectState.status === 'dirty'}
							<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Neuloženo
						{:else if projectState.status === 'error'}
							<span class="w-1.5 h-1.5 rounded-full bg-destructive"></span>
							<span class="text-destructive">Uložení selhalo</span>
						{:else if projectState.status === 'saved'}
							<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> {t('saved')}
						{/if}
					</p>
					{#if projectState.error}
						<p class="text-destructive">{projectState.error}</p>
					{/if}
				</div>
			</CardContent>
		</Card>

		{#if selectedNodeId && selectedNodeData}
			<Card class="shadow-sm border-primary">
				<CardHeader class="pb-3">
					<CardTitle class="text-base">{t('nodeDetail')}</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">{t('languageName')}</Label>
						<Input value={selectedNodeData.data.label} oninput={(e) => {
							nodes = nodes.map(n => n.id === selectedNodeId ? { ...n, data: { ...n.data, label: e.currentTarget.value } } : n);
						}} />
					</div>
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">{t('bornYear')}</Label>
						<Input disabled value={selectedNodeData.data.year} />
					</div>
					<div class="flex items-center gap-2 p-2 rounded-md border {(selectedNodeData.data as any).isDead ? 'bg-muted border-border' : 'bg-background'}">
						<Checkbox id="isDead" checked={(selectedNodeData.data as any).isDead || false} onchange={(e: Event & { currentTarget: HTMLInputElement }) => setDead(selectedNodeId!, e.currentTarget.checked)} />
						<Label for="isDead" class="text-sm font-medium cursor-pointer">{t('deadLanguage')}</Label>
					</div>
				</CardContent>
			</Card>

		{/if}
	</div>

	<!-- Right Panel: Language Detail Sidebar -->
	{#if selectedNodeId && selectedNodeData && detailOpen}
		<div class="absolute top-0 right-0 bottom-0 z-20 shadow-2xl animate-in slide-in-from-right">
			<LanguageDetail
				runId={projectState.simulationRunId}
				nodeId={selectedNodeId}
				label={String(selectedNodeData.data.label ?? selectedNodeId)}
				biome={(selectedNodeData.data as any).biome ?? null}
				years={Math.max(0, timeSteps[currentTimeIndex] - Number(selectedNodeData.data.year || 0))}
				currentYear={timeSteps[currentTimeIndex]}
				embedded={false}
				onclose={() => (detailOpen = false)}
				onIsogloss={handleIsogloss}
			/>
		</div>
	{/if}

	<TimelineControl
		{timeSteps}
		currentIndex={currentTimeIndex}
		onChange={(index) => (currentTimeIndex = index)}
		onAdd={addTimeStep}
	/>

</div>

<style>
	/* Hrany reagují na kurzor, ať je vůbec možné je vybrat a smazat. */
	:global(.svelte-flow__edge) {
		cursor: pointer;
	}

	:global(.svelte-flow__edge .svelte-flow__edge-interaction) {
		stroke-width: 18;
	}

	/* Kontakt se kreslí přerušovaně, aby šel odlišit od dědičnosti. */
	:global(.svelte-flow__edge.animated .svelte-flow__edge-path) {
		stroke-dasharray: 6 5;
	}

	:global(.svelte-flow__edge.selected .svelte-flow__edge-path) {
		stroke: #ef4444;
		stroke-width: 2.4;
		opacity: 1;
	}

	/* Skrýt handles v režimu posunu (move), aby uživatel neomylem nevykreslil hranu */
	:global(.tool-interact .svelte-flow__handle) {
		pointer-events: none !important;
	}
	:global(.tool-relationship .svelte-flow__handle) {
		pointer-events: auto !important;
	}

	@keyframes fillProgress {
		0% { width: 0%; opacity: 0.8; }
		100% { width: 100%; opacity: 0; }
	}
</style>
