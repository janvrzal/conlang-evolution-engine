<script lang="ts">
	import { page } from '$app/stores';
	import {
		SvelteFlow,
		Controls,
		Background,
		BackgroundVariant,
		ConnectionLineType,
		ConnectionMode
	} from '@xyflow/svelte';
	import type { Node, Edge } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	
	import LanguageNode from '$lib/LanguageNode.svelte';
	import LanguageDetail from '$lib/LanguageDetail.svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { MousePointer2, GitCommitHorizontal, X, Download, Trash2 } from 'lucide-svelte';
	
	import { simulateDynamic, resetApiBase } from '$lib/api';
	import { projectState, loadProject, scheduleSave, flushSave } from '$lib/state.svelte';
	import { onMount } from 'svelte';

	const nodeTypes = {
		language: LanguageNode
	};

	// Obsidian kreslí spoje jako rovné čáry. Výchozí bezier se u uzlů nad sebou
	// zamotává do smyček, které nic neznamenají.
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

	// Sync current step to view
	$effect(() => {
		if (!projectState.loaded) return;
		const year = timeSteps[currentTimeIndex];
		if (!snapshots[year]) {
			// Copy from the previous available snapshot
			const prevYear = timeSteps[currentTimeIndex - 1];
			if (prevYear !== undefined && snapshots[prevYear]) {
				projectState.snapshots[year] = {
					nodes: JSON.parse(JSON.stringify(snapshots[prevYear].nodes)),
					edges: JSON.parse(JSON.stringify(snapshots[prevYear].edges))
				};
			} else {
				projectState.snapshots[year] = { nodes: [], edges: [] };
			}
		}
		
		nodes = snapshots[year].nodes;
		edges = snapshots[year].edges;
	});

	// Save back to snapshot
	$effect(() => {
		if (!projectState.loaded) return;
		const year = timeSteps[currentTimeIndex];
		if (projectState.snapshots[year]) {
			projectState.snapshots[year].nodes = nodes;
			projectState.snapshots[year].edges = edges;
		}
	});

	// --- Interaction Logic (Toolbar) ---
	let activeTool = $state<'move' | 'connect'>('connect');

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
			const topologyNodes: Record<string, { biome: string }> = {};
			for (const n of nodes) {
				topologyNodes[n.id] = { biome: (n.data as any).biome ?? 'none' };
			}

			const topology_data = {
				nodes: topologyNodes,
				edges: edges.map((e) => ({ source: e.source, target: e.target }))
			};

			const data = await simulateDynamic({
				topology_data,
				proto_lexicon: projectState.generatedProtoLexicon
			});

			if (data.status === 'success') {
				projectState.simulationResult = data;
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
			onedgeclick={onEdgeClick}
			onedgecontextmenu={onEdgeContextMenu}
			{defaultEdgeOptions}
			connectionLineType={ConnectionLineType.Straight}
			connectionMode={ConnectionMode.Loose}
			nodesDraggable={activeTool === 'move'}
			nodesConnectable={activeTool === 'connect'}
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
			Spojení
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
