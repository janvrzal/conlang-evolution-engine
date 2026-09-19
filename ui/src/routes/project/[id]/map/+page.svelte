<script lang="ts">
	import { page } from '$app/stores';
	import {
		SvelteFlow,
		Controls,
		Background,
		BackgroundVariant,
		ConnectionLineType,
		ConnectionMode,
		ViewportPortal,
		addEdge,
		type Node,
		type Edge
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';

	import LanguageNode from '$lib/LanguageNode.svelte';
	import ContactEdge from '$lib/ContactEdge.svelte';
	import TimelineControl from '$lib/TimelineControl.svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Label } from '$lib/components/ui/label';
	import MapToolbar from '$lib/MapToolbar.svelte';
	import MapProjectPanel from '$lib/MapProjectPanel.svelte';
	import HomophonyQueue, { type PendingHomophony } from '$lib/HomophonyQueue.svelte';

	import {
		simulateDynamic,
		resetApiBase,
		fetchRunExport,
		importLegacyNeo4j,
		fetchSchemaProfiles,
		fetchPhoibleStatus,
		updatePhoibleData,
		fetchRunMetrics,
		fetchGrammar,
		fetchEdgeRules,
		type SchemaProfile,
		type PhoibleStatus
	} from '$lib/api';
	import { projectState, loadProject, scheduleSave, flushSave } from '$lib/state.svelte';
	import {
		propagateSnapshots,
		findEdgeBetween,
		retypeEdge,
		newEdgeFields,
		snapshotForCanvas
	} from '$lib/timeline';
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

	let schemaProfiles = $state<SchemaProfile[]>([]);
	let phoible = $state<PhoibleStatus | null>(null);
	let metrics = $state<any>(null);
	let grammar = $state('');
	let edgeRules = $state<any[]>([]);
	let pendingHomophones = $state<PendingHomophony[]>([]);
	let resourceLoading = $state(false);
	let selectedProfile = $derived(
		schemaProfiles.find((profile) => profile.id === projectState.schemaProfileId)
	);

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
	onMount(() => {
		// Protojazyk zakládá store, ne tenhle callback — jinak ho stihne přebít
		// synchronizační efekt níž a do projektu se uloží prázdný snapshot.
		void loadProject($page.params.id ?? 'default');
		void loadSimulationControls();

		const flush = () => void flushSave();
		window.addEventListener('beforeunload', flush);
		window.addEventListener('keydown', onKeyDown);
		return () => {
			window.removeEventListener('beforeunload', flush);
			window.removeEventListener('keydown', onKeyDown);
		};
	});

	async function loadSimulationControls() {
		try {
			[schemaProfiles, phoible] = await Promise.all([fetchSchemaProfiles(), fetchPhoibleStatus()]);
			if (projectState.simulationRunId)
				metrics = await fetchRunMetrics(projectState.simulationRunId);
			if (projectState.simulationRunId) await loadHomophonyQueue(projectState.simulationRunId);
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : String(e);
		}
	}

	async function loadHomophonyQueue(runId: string) {
		const payload = await fetchRunExport(runId);
		pendingHomophones = (payload.events ?? [])
			.filter((event: any) => event.kind === 'homophony_pending' && event.status === 'pending')
			.filter((event: any) => {
				const decision = projectState.homophonyQueue[event.decision_id];
				return (
					decision !== 'dismissed' &&
					!(typeof decision === 'object' && decision.status === 'resolved')
				);
			})
			.map((event: any) => ({
				...event,
				reviewState:
					projectState.homophonyQueue[event.decision_id] === 'reviewing' ? 'reviewing' : undefined
			}));
	}

	function resolveHomophony(item: PendingHomophony, action: 'review' | 'dismiss') {
		projectState.homophonyQueue = {
			...projectState.homophonyQueue,
			[item.decision_id]: action === 'dismiss' ? 'dismissed' : 'reviewing'
		};
		scheduleSave();
		if (action === 'dismiss') {
			pendingHomophones = pendingHomophones.filter(
				(candidate) => candidate.decision_id !== item.decision_id
			);
			return;
		}
		window.location.assign(
			`/project/${projectState.id}/languages/${item.language_id}?year=${item.year}&homophony=${encodeURIComponent(item.decision_id)}`
		);
	}

	async function refreshPhoible() {
		resourceLoading = true;
		try {
			phoible = await updatePhoibleData();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : String(e);
		} finally {
			resourceLoading = false;
		}
	}

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
	let activeTool = $state<'interact' | 'relationship' | 'route'>('interact');
	let relationshipType = $state<'inheritance' | 'contact'>('inheritance');
	let drawingRouteId = $state<string | null>(null);
	// Kreslení je záměrně modální akce. Když se autor vrátí k běžné interakci
	// nebo k tvorbě vztahu, nesmí další klik omylem přidat bod do staré trasy.
	$effect(() => {
		if (activeTool !== 'route') drawingRouteId = null;
	});

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

		const existingIdx = findEdgeBetween(
			edges as unknown as TLEdge[],
			connection.source,
			connection.target
		);
		if (existingIdx !== -1) {
			edges = edges.map((e, i) =>
				i === existingIdx
					? (retypeEdge(e as unknown as TLEdge, wantsContact, year) as unknown as Edge)
					: e
			);
			return;
		}

		// Explicitní `id` ve stejném formátu jako generuje `addEdge()` samo —
		// bez něj TS spojuje objekt s "Edge" větví typu Connection | Edge
		// a stěžuje si na chybějící povinné `id`, i když by šlo o platné
		// nové spojení (addEdge() by si id doplnil sám).
		edges = addEdge(
			{
				id: `xy-edge__${connection.source}-${connection.target}`,
				...connection,
				...newEdgeFields(wantsContact, year)
			},
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

	function updateNodeSocial(
		nodeId: string,
		field: 'prestige' | 'mobility' | 'standardization',
		value: number
	) {
		nodes = nodes.map((node) =>
			node.id === nodeId
				? {
						...node,
						data: { ...node.data, social: { ...((node.data as any).social ?? {}), [field]: value } }
					}
				: node
		);
	}

	function setLexicalHistory(nodeId: string, enabled: boolean) {
		nodes = nodes.map((node) =>
			node.id === nodeId
				? {
						...node,
						data: { ...node.data, lexical: { ...((node.data as any).lexical ?? {}), enabled } }
					}
				: node
		);
	}

	// Selection
	let selectedNodeId = $state<string | null>(null);
	let selectedNodeData = $derived(nodes.find((n) => n.id === selectedNodeId));

	// xyflow v1 (Svelte 5) předává handlery jako callback props, ne přes on:.
	// Direktiva `on:nodeclick` se nikdy nespustila, takže panel nešlo otevřít.
	function onNodeClick({ node }: { node: Node }) {
		selectedNodeId = node.id;
		detailOpen = true;
		if (projectState.simulationRunId) {
			void fetchGrammar(projectState.simulationRunId, node.id)
				.then((value) => (grammar = value))
				.catch(() => (grammar = ''));
		}
	}

	function toggleRouteDrawing(routeId: string) {
		drawingRouteId = drawingRouteId === routeId ? null : routeId;
		if (drawingRouteId) activeTool = 'route';
	}

	function onPaneClick({ event }: { event: MouseEvent }) {
		if (activeTool === 'route' && drawingRouteId) {
			const canvas = document.querySelector('.svelte-flow') as HTMLElement | null;
			const viewport = canvas?.querySelector('.svelte-flow__viewport') as HTMLElement | null;
			const bounds = canvas?.getBoundingClientRect();
			if (!bounds || !viewport) return;
			const matrix = new DOMMatrix(getComputedStyle(viewport).transform);
			const zoom = matrix.a || 1;
			const point = {
				x: Math.round((event.clientX - bounds.left - matrix.e) / zoom),
				y: Math.round((event.clientY - bounds.top - matrix.f) / zoom)
			};
			projectState.tradeRoutes = projectState.tradeRoutes.map((route) =>
				route.id === drawingRouteId
					? { ...route, waypoints: [...(route.waypoints ?? []), point] }
					: route
			);
			scheduleSave();
			return;
		}
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
			alert('Nejprve vygeneruj testovací slovník v sekci Metaeditace!');
			return;
		}

		isLoading = true;
		errorMessage = '';
		// Artificial minimum wait to show the progress bar if the API is too fast
		const minWait = new Promise((resolve) => setTimeout(resolve, 800));

		try {
			// Backend musí dostat celou historii mapy. Dědičnost žije jen v
			// okamžiku odštěpení; v dalších snímcích se správně mění na kontakt.
			// Poslat jen aktuálně zobrazený snímek by proto genealogii zahodilo.
			const topology_data = {
				polities: projectState.polities,
				tradeRoutes: projectState.tradeRoutes,
				historicalEvents: projectState.historicalEvents,
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
				run_id: projectState.simulationRunId,
				schema_profile_id: projectState.schemaProfileId,
				empirical_phonology: projectState.empiricalPhonology,
				calibration: projectState.calibration
			});

			await minWait;

			if (data.status === 'success') {
				projectState.simulationRunAt = new Date().toISOString();
				projectState.simulationRunId = data.run_id;
				metrics = await fetchRunMetrics(data.run_id);
				await loadHomophonyQueue(data.run_id);
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
			console.error('Chyba při volání API', e);
		} finally {
			isLoading = false;
		}
	}

	$effect(() => {
		const selected = edges.find((edge) => edge.id === selectedEdgeId);
		if (!selected || selected.type === 'contact' || !projectState.simulationRunId) {
			edgeRules = [];
			return;
		}
		void fetchEdgeRules(projectState.simulationRunId, selected.target)
			.then((rules) => (edgeRules = rules))
			.catch(() => (edgeRules = []));
	});
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
				<!--
					Podklad patří do stejného transformovaného viewportu jako uzly.
					Je ukotvený ve světovém počátku (0, 0), takže při posouvání
					nebo přibližování plátna cestuje i mění měřítko spolu s jazyky.
				-->
				{#if projectState.mapBackground}
					<ViewportPortal
						target="back"
						class="pointer-events-none overflow-visible"
						aria-hidden="true"
					>
						<img
							src={projectState.mapBackground.dataUrl}
							alt=""
							class="map-background absolute left-0 top-0 max-w-none select-none"
							style={`--map-scale: ${projectState.mapBackground.scale / 100}; opacity: ${projectState.mapBackground.opacity};`}
						/>
					</ViewportPortal>
				{/if}
				{#each projectState.tradeRoutes as route (route.id)}
					{#if (route.waypoints ?? []).length > 1}
						<ViewportPortal
							target="back"
							class="pointer-events-none overflow-visible"
							aria-hidden="true"
						>
							<svg class="absolute left-0 top-0 overflow-visible" width="1" height="1">
								<polyline
									points={route.waypoints
										.map((point: { x: number; y: number }) => `${point.x},${point.y}`)
										.join(' ')}
									fill="none"
									stroke={route.id === drawingRouteId
										? 'hsl(var(--primary))'
										: 'hsl(var(--muted-foreground))'}
									stroke-width="5"
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-dasharray={route.kind === 'sea'
										? '12 8'
										: route.kind === 'river'
											? '4 7'
											: undefined}
									opacity="0.7"
								/>
							</svg>
						</ViewportPortal>
					{/if}
				{/each}
				<Background variant={BackgroundVariant.Dots} gap={28} size={1} class="opacity-30" />
				<Controls class="bg-card border-border fill-foreground" />
			</SvelteFlow>
		{/key}
	</div>

	<MapToolbar
		bind:activeTool
		bind:relationshipType
		{selectedEdgeId}
		onDeleteEdge={deleteSelectedEdge}
	/>

	<!-- Left Panel: Project Settings -->
	<div class="absolute top-4 left-4 bottom-4 z-10 w-80 space-y-4 overflow-y-auto pr-1">
		<MapProjectPanel
			currentYear={timeSteps[currentTimeIndex]}
			{drawingRouteId}
			onDrawRoute={toggleRouteDrawing}
			{isLoading}
			{errorMessage}
			onAddLanguage={addLanguage}
			onRunSimulation={runSimulation}
			onExport={exportSimulation}
			onImportLegacy={importPreviousSimulation}
		/>

		<Card class="shadow-sm">
			<CardHeader class="pb-2"><CardTitle class="text-base">Simulační profil</CardTitle></CardHeader
			>
			<CardContent class="space-y-3">
				<label class="block text-xs font-medium">
					Váhy zvukových změn
					<select
						class="mt-1 w-full h-9 rounded-md border border-input bg-background px-2 text-sm"
						value={projectState.schemaProfileId}
						onchange={(event) => {
							projectState.schemaProfileId = event.currentTarget.value;
							scheduleSave();
						}}
					>
						{#each schemaProfiles as profile (profile.id)}
							<option value={profile.id}>{profile.label}</option>
						{/each}
					</select>
				</label>
				{#if selectedProfile}
					<p class="text-xs text-muted-foreground">{selectedProfile.description}</p>
				{/if}
				<div class="border-t pt-3 space-y-3">
					<p class="text-xs font-medium">Tempo a šíření</p>
					<label class="block text-xs text-muted-foreground">
						Inovace / tisíc let: {projectState.calibration.sound_changes_per_millennium}
						<Input
							type="range"
							min="2"
							max="24"
							step="1"
							bind:value={projectState.calibration.sound_changes_per_millennium}
							oninput={scheduleSave}
						/>
					</label>
					<label class="block text-xs text-muted-foreground">
						Šíření změny: {projectState.calibration.change_spread_years} let
						<Input
							type="range"
							min="0"
							max="240"
							step="10"
							bind:value={projectState.calibration.change_spread_years}
							oninput={scheduleSave}
						/>
					</label>
					<label class="block text-xs text-muted-foreground">
						Izolovanost: {Math.round(projectState.calibration.isolation * 100)} %
						<Input
							type="range"
							min="0"
							max="1"
							step="0.05"
							bind:value={projectState.calibration.isolation}
							oninput={scheduleSave}
						/>
					</label>
				</div>
				<div class="border-t pt-3 space-y-2">
					<div class="flex items-center justify-between gap-2">
						<div>
							<p class="text-xs font-medium">Empirická fonologie (PHOIBLE)</p>
							<p class="text-xs text-muted-foreground">
								{phoible?.available
									? `${phoible.inventories ?? 0} inventářů v lokální cache`
									: 'Cache zatím není stažená'}
							</p>
						</div>
						<input
							type="checkbox"
							checked={projectState.empiricalPhonology}
							disabled={!phoible?.available}
							onchange={(event) => {
								projectState.empiricalPhonology = event.currentTarget.checked;
								scheduleSave();
							}}
						/>
					</div>
					<Button
						variant="outline"
						size="sm"
						class="w-full"
						onclick={refreshPhoible}
						disabled={resourceLoading}
					>
						{resourceLoading
							? 'Aktualizuji PHOIBLE…'
							: phoible?.available
								? 'Aktualizovat PHOIBLE'
								: 'Stáhnout PHOIBLE'}
					</Button>
				</div>
			</CardContent>
		</Card>

		{#if metrics}
			<Card class="shadow-sm">
				<CardHeader class="pb-2"><CardTitle class="text-base">Validace běhu</CardTitle></CardHeader>
				<CardContent class="space-y-1 text-xs">
					<p>Aplicované změny: <strong>{metrics.sound_changes}</strong></p>
					{#if metrics.sound_change_phases}
						<p>Fáze šíření: <strong>{metrics.sound_change_phases}</strong></p>
					{/if}
					<p>
						Změny / tisíciletí: <strong
							>{Number(metrics.changes_per_millennium ?? 0).toFixed(2)}</strong
						>
					</p>
					<p>Smazané segmenty: <strong>{metrics.deleted_segments}</strong></p>
					{#if Object.keys(metrics.schemas ?? {}).length}
						<p class="pt-1 text-muted-foreground">
							{Object.entries(metrics.schemas)
								.map(([id, count]) => `${id}: ${count}`)
								.join(' · ')}
						</p>
					{/if}
				</CardContent>
			</Card>
		{/if}

		{#if selectedEdgeId && edgeRules.length}
			<Card class="shadow-sm border-primary">
				<CardHeader class="pb-2"
					><CardTitle class="text-base">Pravidla na hraně</CardTitle></CardHeader
				>
				<CardContent class="space-y-2 text-xs">
					{#each edgeRules as rule (rule.year + rule.rule)}
						<div class="border-b pb-1">
							<strong>{rule.year}: {rule.rule}</strong>
							<div class="text-muted-foreground">
								{rule.schema_id} · zásahy {rule.hit_count} · smazáno {rule.deleted_segments}
							</div>
						</div>
					{/each}
				</CardContent>
			</Card>
		{/if}

		{#if grammar}
			<Card class="shadow-sm">
				<CardHeader class="pb-2"
					><CardTitle class="text-base">Gramatický náčrt</CardTitle></CardHeader
				>
				<CardContent><pre class="text-xs whitespace-pre-wrap font-sans">{grammar}</pre></CardContent
				>
			</Card>
		{/if}

		{#if selectedNodeId && selectedNodeData && !detailOpen}
			<Card class="shadow-sm border-primary">
				<CardHeader class="pb-3">
					<CardTitle class="text-base">{t('nodeDetail')}</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">{t('languageName')}</Label>
						<Input
							value={selectedNodeData.data.label}
							oninput={(e) => {
								nodes = nodes.map((n) =>
									n.id === selectedNodeId
										? { ...n, data: { ...n.data, label: e.currentTarget.value } }
										: n
								);
							}}
						/>
					</div>
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">{t('bornYear')}</Label>
						<Input disabled value={selectedNodeData.data.year} />
					</div>
					<div
						class="flex items-center gap-2 p-2 rounded-md border {(selectedNodeData.data as any)
							.isDead
							? 'bg-muted border-border'
							: 'bg-background'}"
					>
						<Checkbox
							id="isDead"
							checked={(selectedNodeData.data as any).isDead || false}
							onchange={(e: Event & { currentTarget: HTMLInputElement }) =>
								setDead(selectedNodeId!, e.currentTarget.checked)}
						/>
						<Label for="isDead" class="text-sm font-medium cursor-pointer"
							>{t('deadLanguage')}</Label
						>
					</div>
					<div class="space-y-2 border rounded-md p-3">
						<Label class="text-xs font-semibold">{t('socialProfile')}</Label>
						{#each [['prestige', t('prestige')], ['mobility', t('mobility')], ['standardization', t('standardization')]] as [field, label]}
							<label class="block text-xs text-muted-foreground">
								<span class="flex justify-between"
									><span>{label}</span><span
										>{Math.round(
											Number((selectedNodeData.data as any).social?.[field] ?? 0.5) * 100
										)}%</span
									></span
								>
								<Input
									type="range"
									min="0"
									max="1"
									step="0.05"
									value={Number((selectedNodeData.data as any).social?.[field] ?? 0.5)}
									oninput={(e) =>
										updateNodeSocial(
											selectedNodeId!,
											field as 'prestige' | 'mobility' | 'standardization',
											parseFloat(e.currentTarget.value)
										)}
								/>
							</label>
						{/each}
					</div>
					<div class="flex items-center gap-2 p-2 rounded-md border">
						<Checkbox
							id="lexical-history"
							checked={(selectedNodeData.data as any).lexical?.enabled ?? false}
							onchange={(e: Event & { currentTarget: HTMLInputElement }) =>
								setLexicalHistory(selectedNodeId!, e.currentTarget.checked)}
						/>
						<Label for="lexical-history" class="text-sm font-medium cursor-pointer"
							>{t('enableLexicalHistory')}</Label
						>
					</div>
				</CardContent>
			</Card>
		{/if}
	</div>

	<!-- Right Panel: Language Detail Sidebar -->
	{#if projectState.simulationRunId}
		<div class="absolute right-6 bottom-36 z-20">
			<HomophonyQueue items={pendingHomophones} onResolve={resolveHomophony} />
		</div>
	{/if}

	{#if selectedNodeId && selectedNodeData && detailOpen}
		<div class="absolute right-4 top-4 z-20 w-72 animate-in slide-in-from-right">
			<Card class="shadow-lg border-primary">
				<CardHeader class="pb-2"
					><CardTitle class="text-base">Nastavení jazyka</CardTitle></CardHeader
				>
				<CardContent class="space-y-3">
					<label class="block text-xs text-muted-foreground"
						>Název
						<Input
							value={selectedNodeData.data.label}
							oninput={(e) => {
								nodes = nodes.map((n) =>
									n.id === selectedNodeId
										? { ...n, data: { ...n.data, label: e.currentTarget.value } }
										: n
								);
								scheduleSave();
							}}
						/>
					</label>
					<div class="space-y-2 border rounded-md p-3">
						<Label class="text-xs font-semibold">Sociální profil</Label>
						{#each [['prestige', t('prestige')], ['mobility', t('mobility')], ['standardization', t('standardization')]] as [field, label]}
							<label class="block text-xs text-muted-foreground"
								>{label}: {Math.round(
									Number((selectedNodeData.data as any).social?.[field] ?? 0.5) * 100
								)}%
								<Input
									type="range"
									min="0"
									max="1"
									step="0.05"
									value={Number((selectedNodeData.data as any).social?.[field] ?? 0.5)}
									oninput={(e) =>
										updateNodeSocial(
											selectedNodeId!,
											field as 'prestige' | 'mobility' | 'standardization',
											parseFloat(e.currentTarget.value)
										)}
								/>
							</label>
						{/each}
					</div>
					<div class="flex items-center gap-2 rounded-md border p-2">
						<Checkbox
							id="node-lexical-history"
							checked={(selectedNodeData.data as any).lexical?.enabled ?? false}
							onchange={(e: Event & { currentTarget: HTMLInputElement }) =>
								setLexicalHistory(selectedNodeId!, e.currentTarget.checked)}
						/><Label for="node-lexical-history" class="text-sm">{t('enableLexicalHistory')}</Label>
					</div>
					<Button
						variant="outline"
						class="w-full"
						href={`/project/${projectState.id}/languages/${selectedNodeId}?year=${timeSteps[currentTimeIndex]}`}
					>
						Spravovat jazyk
					</Button>
				</CardContent>
			</Card>
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
	.map-background {
		transform: scale(var(--map-scale));
		transform-origin: left top;
	}

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
</style>
