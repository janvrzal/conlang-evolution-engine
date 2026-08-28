<script lang="ts">
	import { page } from '$app/stores';
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
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import {
		MousePointer2,
		GitCommitHorizontal,
		ArrowLeftRight,
		X,
		Download,
		Trash2
	} from 'lucide-svelte';
	
	import { simulateDynamic, resetApiBase } from '$lib/api';
	import { projectState, loadProject, scheduleSave, flushSave } from '$lib/state.svelte';
	import { propagateSnapshots } from '$lib/timeline';
	import { onMount, untrack } from 'svelte';

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

	type BranchData = {
		year: number;
		words: { id: string; ipa: string; polysemy: string[] }[];
		inventory: string[];
		grammar_md: string;
	};

	let branches = $derived(
		Object.entries(
			(projectState.simulationResult?.branches ?? {}) as Record<string, BranchData>
		)
	);

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

		nodes = projectState.snapshots[year].nodes;
		edges = projectState.snapshots[year].edges;
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
	let activeTool = $state<'move' | 'connect' | 'contact'>('connect');

	/** Nová hrana dostane druh podle právě zvoleného nástroje. */
	function onConnect(connection: { source: string; target: string }) {
		const year = timeSteps[currentTimeIndex];
		
		let newEdge: any = { ...connection };
		if (activeTool === 'contact') {
			newEdge.type = 'contact';
			newEdge.data = { contactType: 'neighborhood', intensity: 50, direction: 'ab', year };
		} else {
			newEdge.data = { year };
		}
		
		edges = addEdge(newEdge, edges);
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
		const newNode = {
			id: `lang-${Date.now()}`,
			type: 'language',
			position: { x: Math.random() * 300 + 200, y: Math.random() * 300 + 200 },
			data: { label: `Nový jazyk`, year }
		};
		nodes = [...nodes, newNode];
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
	let minYear = $derived(Math.min(...timeSteps));
	let maxYear = $derived(Math.max(...timeSteps, minYear + 1)); // prevent division by zero
	let timeSpan = $derived(maxYear - minYear || 1);

	// --- Simulation Logic ---
	let isLoading = $state(false);
	let errorMessage = $state('');
	let showResultsModal = $state(false);

	async function runSimulation() {
		if (projectState.generatedProtoLexicon.length === 0) {
			alert("Nejprve vygeneruj testovací slovník v sekci Metaeditace!");
			return;
		}
		
		isLoading = true;
		errorMessage = '';
		try {
			// Sestavení topologie pro backend
			const topologyNodes: Record<string, { biome: string, society: string }> = {};
			for (const n of nodes) {
				topologyNodes[n.id] = { 
					biome: (n.data as any).biome ?? 'none',
					society: (n.data as any).society ?? 'none'
				};
			}

			const topology_data = {
				nodes: topologyNodes,
				edges: edges.map((e) => {
					return e.type === 'contact'
						? {
								source: e.source,
								target: e.target,
								kind: 'contact',
								contactType: (e.data as any)?.contactType ?? 'neighborhood',
								intensity: (e.data as any)?.intensity ?? 50,
								direction: (e.data as any)?.direction ?? 'ab',
								year: (e.data as any)?.year ?? Math.round(maxYear / 2),
								volume: (e.data as any)?.volume ?? 5,
								mutual: (e.data as any)?.mutual ?? true
							}
						: { source: e.source, target: e.target, kind: 'inheritance' };
				})
			};

			const data = await simulateDynamic({
				topology_data,
				proto_lexicon: projectState.generatedProtoLexicon,
				years: maxYear
			});

			if (data.status === 'success') {
				projectState.simulationResult = data;
				projectState.simulationRunAt = new Date().toISOString();
				// Výsledek je hlavní výstup — ať přežije reload, uložíme hned.
				void flushSave();
				showResultsModal = true;
			} else {
				errorMessage = `Engine vrátil stav '${data.status}'.`;
			}
		} catch (e) {
			resetApiBase();
			errorMessage = e instanceof Error ? e.message : String(e);
			console.error("Chyba při volání API", e);
		} finally {
			isLoading = false;
		}
	}
	
	function downloadCSV(branchId: string, branchData: any) {
		const header = 'id,ipa,polysemy\n';
		const rows = branchData.words.map((w: any) => `${w.id},${w.ipa},${w.polysemy.join('|')}`).join('\n');
		const csvContent = "data:text/csv;charset=utf-8," + header + rows;
		
		const encodedUri = encodeURI(csvContent);
		const link = document.createElement("a");
		link.setAttribute("href", encodedUri);
		link.setAttribute("download", `${branchId}_lexicon.csv`);
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
	}

	function downloadMarkdown(branchId: string, branchData: any) {
		const mdContent = "data:text/markdown;charset=utf-8," + encodeURIComponent(branchData.grammar_md);
		
		const link = document.createElement("a");
		link.setAttribute("href", mdContent);
		link.setAttribute("download", `${branchId}_grammar.md`);
		document.body.appendChild(link);
		link.click();
		document.body.removeChild(link);
	}
</script>

<svelte:head>
	<title>Mapa | Projekt {$page.params.id}</title>
</svelte:head>

<div class="relative w-full h-screen bg-background overflow-hidden flex tool-{activeTool}">
	<!-- Canvas -->
	<div class="absolute inset-0">
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
			nodesDraggable={activeTool === 'move'}
			nodesConnectable={activeTool === 'connect' || activeTool === 'contact'}
			onconnect={onConnect}
			elementsSelectable={true}
			onnodeclick={onNodeClick}
			onpaneclick={onPaneClick}
			fitView
		>
			<Background variant={BackgroundVariant.Dots} gap={28} size={1} class="opacity-30" />
			<Controls class="bg-card border-border fill-foreground" />
		</SvelteFlow>
	</div>

	<!-- Toolbar Panel -->
	<div class="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex bg-card rounded-md border shadow-sm p-1 gap-1">
		<Button 
			variant={activeTool === 'move' ? 'default' : 'ghost'} 
			size="sm" 
			class="px-3"
			onclick={() => activeTool = 'move'}
			title="Nástroj pro posun (Move)"
		>
			<MousePointer2 class="w-4 h-4 mr-2" />
			Posun
		</Button>
		<Button 
			variant={activeTool === 'connect' ? 'default' : 'ghost'} 
			size="sm" 
			class="px-3"
			onclick={() => activeTool = 'connect'}
			title="Nástroj pro spojení (Connect)"
		>
			<GitCommitHorizontal class="w-4 h-4 mr-2" />
			Dědičnost
		</Button>
		<Button
			variant={activeTool === 'contact' ? 'default' : 'ghost'}
			size="sm"
			class="px-3"
			onclick={() => (activeTool = 'contact')}
			title="Kontakt — sousedé, kteří se navzájem ovlivňují (výpůjčky)"
		>
			<ArrowLeftRight class="w-4 h-4 mr-2" />
			Kontakt
		</Button>
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

	<!-- Left Panel: Project Settings -->
	<div class="absolute top-4 left-4 z-10 w-64 flex flex-col gap-4">
		<Card class="shadow-sm">
			<CardHeader class="pb-3">
				<CardTitle class="text-lg">Projekt: {$page.params.id}</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<Button class="w-full" variant="outline" size="sm" onclick={addLanguage}>
					+ Přidat uzel
				</Button>
				<Button class="w-full" variant="default" size="sm" onclick={runSimulation} disabled={isLoading}>
					{isLoading ? 'Simuluji...' : 'Spustit Vývoj (Simulovat)'}
				</Button>
				{#if errorMessage}
					<p class="text-xs text-destructive">{errorMessage}</p>
				{/if}
				{#if projectState.simulationResult}
					<Button class="w-full" variant="secondary" size="sm" onclick={() => showResultsModal = true}>
						Zobrazit výsledky simulace
					</Button>
				{/if}
				<div class="text-xs text-muted-foreground space-y-1">
					<p>Aktuální krok: <strong>Rok {timeSteps[currentTimeIndex]}</strong></p>
					<p class="flex items-center gap-1.5">
						{#if projectState.status === 'saving'}
							<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Ukládám…
						{:else if projectState.status === 'dirty'}
							<span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Neuloženo
						{:else if projectState.status === 'error'}
							<span class="w-1.5 h-1.5 rounded-full bg-destructive"></span>
							<span class="text-destructive">Uložení selhalo</span>
						{:else if projectState.status === 'saved'}
							<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Uloženo
						{/if}
					</p>
					{#if projectState.error}
						<p class="text-destructive">{projectState.error}</p>
					{/if}
				</div>
			</CardContent>
		</Card>
	</div>

	<!-- Right Panel: drill-down vývoje jazyka -->
	{#if detailOpen && selectedNodeId && selectedNodeData}
		<div class="absolute top-0 right-0 bottom-0 z-20">
			<LanguageDetail
				nodeId={selectedNodeId}
				label={String(selectedNodeData.data.label ?? selectedNodeId)}
				biome={(selectedNodeData.data as any).biome ?? null}
				years={timeSteps[timeSteps.length - 1] ?? 1000}
				lexicon={projectState.generatedProtoLexicon}
				onclose={() => (detailOpen = false)}
			/>
		</div>
	{/if}

	<!-- Rychlá editace uzlu -->
	{#if selectedNodeId && selectedNodeData && !detailOpen}
		<div class="absolute top-4 right-4 z-10 w-72">
			<Card class="shadow-sm border-primary">
				<CardHeader class="pb-3">
					<CardTitle class="text-base">Detail uzlu</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">Název jazyka</Label>
						<Input value={selectedNodeData.data.label} oninput={(e) => {
							nodes = nodes.map(n => n.id === selectedNodeId ? { ...n, data: { ...n.data, label: e.currentTarget.value } } : n);
						}} />
					</div>
					<div class="space-y-1.5">
						<Label class="text-xs text-muted-foreground">Vznik v roce</Label>
						<Input disabled value={selectedNodeData.data.year} />
					</div>
					<div class="flex items-center gap-2 mt-4 p-2 rounded-md border {(selectedNodeData.data as any).isDead ? 'bg-muted border-border' : 'bg-background'}">
						<input
							type="checkbox"
							id="isDead"
							class="accent-primary"
							checked={(selectedNodeData.data as any).isDead || false}
							onchange={(e) => setDead(selectedNodeId!, e.currentTarget.checked)}
						/>
						<Label for="isDead" class="text-sm font-medium cursor-pointer">Jazyk je mrtvý (tombstone)</Label>
					</div>
					<p class="text-[11px] text-muted-foreground -mt-2">
						Zruší všechna jeho spojení od tohoto roku dál — v dřívějších letech zůstávají.
					</p>
					<Button class="w-full mt-2" size="sm">Editovat pravidla</Button>
				</CardContent>
			</Card>
		</div>
	{/if}

	<!-- Minimalist Proportional Timeline -->
	<div class="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 w-full max-w-2xl">
		<div class="bg-card/80 backdrop-blur-md rounded-full border shadow-sm px-8 py-3 flex items-center justify-between gap-4">
			<div class="text-sm font-medium w-16 text-right whitespace-nowrap">Rok {timeSteps[currentTimeIndex]}</div>
			
			<div class="relative flex-1 h-2 bg-muted rounded-full">
				<!-- Current time indicator (progress bar) -->
				<div 
					class="absolute top-0 left-0 h-full bg-primary rounded-full transition-all duration-300"
					style="width: {((timeSteps[currentTimeIndex] - minYear) / timeSpan) * 100}%"
				></div>
				
				<!-- Timeline points -->
				{#each timeSteps as year, i}
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<div 
						class="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 cursor-pointer transition-all hover:scale-125 {i === currentTimeIndex ? 'bg-primary border-background shadow-sm scale-110' : 'bg-background border-primary/50'}"
						style="left: calc({((year - minYear) / timeSpan) * 100}% - 8px)"
						onclick={() => currentTimeIndex = i}
						title="Rok {year}"
					></div>
				{/each}
			</div>

			<Button variant="ghost" size="sm" class="h-8 w-8 p-0 rounded-full shrink-0" onclick={addTimeStep} title="Přidat bod na osu">
				+
			</Button>
		</div>
	</div>

	<!-- Results Modal Overlay -->
	{#if showResultsModal && projectState.simulationResult}
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4" onclick={(e) => { if (e.target === e.currentTarget) showResultsModal = false; }}>
			<div class="bg-card w-full max-w-6xl max-h-[90vh] rounded-xl border shadow-xl flex flex-col overflow-hidden">
				<div class="p-4 border-b flex justify-between items-center bg-muted/30">
					<h2 class="text-xl font-bold">Výsledky Evoluce</h2>
					<Button variant="ghost" size="icon" onclick={() => showResultsModal = false}>
						<X class="w-5 h-5" />
					</Button>
				</div>
				<div class="p-6 overflow-y-auto flex-1 bg-muted/10">
					<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
						{#each branches as [branchId, branchData] (branchId)}
							<Card>
								<CardHeader class="pb-3 border-b bg-card">
									<div class="flex justify-between items-start">
										<div>
											<CardTitle class="text-lg">Jazyk: {branchId}</CardTitle>
											<CardDescription>Rok: {branchData.year}</CardDescription>
										</div>
										<div class="flex gap-2">
											<Button variant="outline" size="sm" onclick={() => downloadCSV(branchId, branchData)} title="Stáhnout slovník (CSV)">
												<Download class="w-4 h-4 mr-1" /> CSV
											</Button>
											<Button variant="outline" size="sm" onclick={() => downloadMarkdown(branchId, branchData)} title="Stáhnout gramatiku (Markdown)">
												<Download class="w-4 h-4 mr-1" /> MD
											</Button>
										</div>
									</div>
								</CardHeader>
								<CardContent class="p-0">
									<div class="max-h-80 overflow-y-auto">
										<table class="w-full text-sm">
											<thead class="bg-muted/50 sticky top-0 backdrop-blur-md">
												<tr>
													<th class="p-2 text-left font-medium">Koncept</th>
													<th class="p-2 text-left font-medium">Slovo (IPA)</th>
													<th class="p-2 text-left font-medium">Významy</th>
												</tr>
											</thead>
											<tbody class="divide-y">
												{#each branchData.words as word}
													<tr class="hover:bg-muted/20">
														<td class="p-2 text-muted-foreground">{word.id}</td>
														<td class="p-2 font-mono font-bold text-primary">{word.ipa}</td>
														<td class="p-2 text-xs italic opacity-75">{word.polysemy.join(', ')}</td>
													</tr>
												{/each}
											</tbody>
										</table>
									</div>
								</CardContent>
							</Card>
						{/each}
					</div>
				</div>
			</div>
		</div>
	{/if}
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
	:global(.tool-move .svelte-flow__handle) {
		display: none !important;
	}
	:global(.tool-connect .svelte-flow__handle) {
		display: block !important;
	}
</style>
