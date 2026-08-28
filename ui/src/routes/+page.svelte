<script lang="ts">
	import { resetApiBase, simulateDynamic, generateProtolangApi } from '$lib/api';
	import { SvelteFlow, Controls, Background, BackgroundVariant } from '@xyflow/svelte';
	import type { Edge, Node } from '@xyflow/svelte';
	import LanguageNode from '$lib/LanguageNode.svelte';
	import '@xyflow/svelte/dist/style.css';

	/** Data, která si k uzlu drží LanguageNode a odesílá se z nich topologie. */
	type LanguageNodeData = {
		label: string;
		isProto?: boolean;
		biome?: string;
	};

	type BranchData = {
		year: number;
		words: { id: string; ipa: string; polysemy: string[] }[];
		grammar_md: string;
	};

	type SimulationResult = {
		status: string;
		branches: Record<string, BranchData>;
		topology: { nodes: { id: string }[]; edges: { source: string; target: string }[] };
	};

	let simulationResult = $state<SimulationResult | null>(null);
	let isLoading = $state(false);
	let errorMessage = $state<string | null>(null);

	// Protolang Forge State
	let consonants = $state('p t k m n s l');
	let vowels = $state('a i u');
	let syllableStructure = $state('(C)V(C)');
	let generatedProtoLexicon = $state<any[]>([]);
	
	// Graph State
	const nodeTypes = {
		language: LanguageNode
	};

	// @xyflow/svelte v1 předává nodes/edges jako $bindable pole, ne jako stores.
	let nodes = $state.raw<Node<LanguageNodeData>[]>([
		{
			id: 'proto',
			type: 'language',
			position: { x: 250, y: 50 },
			data: { label: 'z (Proto-Jazyk)', isProto: true }
		}
	]);

	let edges = $state.raw<Edge[]>([]);
	let nodeCounter = 1;

	function addNode() {
		nodes = [
			...nodes,
			{
				id: `lang_${nodeCounter}`,
				type: 'language',
				position: { x: Math.random() * 400, y: Math.random() * 400 + 100 },
				data: { label: `z${nodeCounter}`, isProto: false }
			}
		];
		nodeCounter++;
	}

	async function generateProtolang() {
		errorMessage = null;
		try {
			const data = await generateProtolangApi({ consonants, vowels, syllable_structure: syllableStructure });
			if (data.status === 'success') {
				generatedProtoLexicon = data.words;
			} else {
				errorMessage = `Generátor vrátil stav '${data.status}'.`;
			}
		} catch (e) {
			resetApiBase();
			errorMessage = e instanceof Error ? e.message : String(e);
			console.error("Chyba při generování Protolangu", e);
		}
	}

	async function runSimulation() {
		if (generatedProtoLexicon.length === 0) {
			alert("Nejprve vygeneruj Protolang slovník!");
			return;
		}
		
		isLoading = true;
		errorMessage = null;
		try {
			// Sestavení topologie pro backend
			const topologyNodes: Record<string, { biome: string }> = {};
			for (const n of nodes) {
				topologyNodes[n.id] = { biome: n.data.biome ?? 'none' };
			}

			const topology_data = {
				nodes: topologyNodes,
				edges: edges.map((e) => ({ source: e.source, target: e.target }))
			};

			const data = await simulateDynamic({
				topology_data,
				proto_lexicon: generatedProtoLexicon
			});

			if (data.status === 'success') {
				simulationResult = data;
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
	<title>Conlang Evolution Engine</title>
</svelte:head>

<div class="dashboard">
	<!-- Levý panel: Ovládání -->
	<aside class="glass-panel sidebar">
		<header>
			<h1>CEE</h1>
			<p>Protolang Forge</p>
		</header>
		
		<div class="controls scroll-y">
			<section class="control-group">
				<h3>Tvorba Protojazyka</h3>
				<div class="input-group">
					<label for="input-consonants" title="Které souhlásky může jazyk používat?">Souhlásky (C)</label>
					<input id="input-consonants" type="text" bind:value={consonants} />
				</div>
				<div class="input-group">
					<label for="input-vowels" title="Které samohlásky může jazyk používat?">Samohlásky (V)</label>
					<input id="input-vowels" type="text" bind:value={vowels} />
				</div>
				<div class="input-group">
					<label for="input-syllable" title="Tvar jedné slabiky. Např. CVC, (C)V. (C) znamená volitelnou hlásku.">Struktura slabiky</label>
					<input id="input-syllable" type="text" bind:value={syllableStructure} />
				</div>
				<button class="btn-primary" onclick={generateProtolang}>Vygenerovat Slovník</button>
				
				{#if generatedProtoLexicon.length > 0}
					<p class="success-text">Vygenerováno {generatedProtoLexicon.length} slov!</p>
				{/if}
			</section>
			
			<section class="control-group">
				<h3>Topologie</h3>
				<button class="btn-secondary" onclick={addNode}>+ Přidat Jazyk</button>
			</section>

			<section class="control-group">
				<h3>Simulace</h3>
				<button class="btn-primary" onclick={runSimulation} disabled={isLoading || generatedProtoLexicon.length === 0}>
					{isLoading ? 'Simuluji vesmír...' : 'Spustit Vývoj'}
				</button>

				{#if errorMessage}
					<div class="error-box">{errorMessage}</div>
				{/if}
			</section>
		</div>
		
		<footer>
			<button class="btn-export">Export Dat</button>
		</footer>
	</aside>

	<!-- Hlavní plátno: Mapa / Strom -->
	<main class="canvas scroll-y" style="align-items: flex-start; justify-content: flex-start; padding: 2rem;">
		{#if !simulationResult && !isLoading}
			<div style="width: 100%; height: 500px; background: rgba(0,0,0,0.2); border-radius: 12px; margin-bottom: 2rem; border: 1px solid rgba(255,255,255,0.1);">
				<SvelteFlow bind:nodes bind:edges {nodeTypes} fitView>
					<Background variant={BackgroundVariant.Dots} bgColor="transparent" />
					<Controls />
				</SvelteFlow>
			</div>
			
			<div class="placeholder-map" style="margin: auto;">
				<h2>Sestav Topologii</h2>
				<p>Propoj uzly pomocí myši. Jakmile máš strom i proto-slovník, klikni na Spustit Vývoj.</p>
			</div>
		{:else if isLoading}
			<div class="placeholder-map" style="margin: auto;">
				<h2 class="pulsing">Evoluce probíhá...</h2>
				<p>Kalkuluji fonologické pravidla a sémantické posuny</p>
			</div>
		{:else if simulationResult}
			<div class="results-container">
				<!-- Vizuální graf (Topologie) -->
				<div class="topology-map glass-panel">
					<h2>Evoluční Graf</h2>
					<div class="topology-nodes">
						{#each simulationResult.topology.nodes as node}
							<div class="t-node">{node.id}</div>
						{/each}
					</div>
					<div class="topology-edges">
						{#each simulationResult.topology.edges as edge}
							<span class="t-edge">{edge.source} ➔ {edge.target}</span>
						{/each}
					</div>
				</div>

				<div class="results-grid">
					{#each Object.entries(simulationResult.branches) as [branchId, branchData] (branchId)}
						<div class="glass-panel branch-card">
							<h3>Jazyk: {branchId}</h3>
							<p class="year">Rok: {branchData.year}</p>
							
							<div class="export-actions">
								<button class="btn-export-small" onclick={() => downloadCSV(branchId, branchData)}>Stáhnout CSV</button>
								<button class="btn-export-small" onclick={() => downloadMarkdown(branchId, branchData)}>Stáhnout Gramatiku</button>
							</div>
							
							<table class="lexicon-table">
							<thead>
								<tr>
									<th>Koncept</th>
									<th>Slovo (IPA)</th>
									<th>Další významy</th>
								</tr>
							</thead>
							<tbody>
								{#each branchData.words as word}
									<tr>
										<td>{word.id}</td>
										<td class="ipa">{word.ipa}</td>
										<td class="polysemy">{word.polysemy.join(', ')}</td>
									</tr>
								{/each}
							</tbody>
							</table>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</main>
</div>

<style>
	.error-box {
		margin-top: 0.75rem;
		padding: 0.6rem 0.75rem;
		border: 1px solid rgba(248, 113, 113, 0.4);
		border-radius: 6px;
		background: rgba(248, 113, 113, 0.1);
		color: #fca5a5;
		font-size: 0.8rem;
		line-height: 1.4;
		word-break: break-word;
	}

	.dashboard {
		display: flex;
		flex: 1;
		height: 100%;
		padding: 1.5rem;
		gap: 1.5rem;
		position: relative;
		z-index: 1;
	}

	.sidebar {
		width: 320px;
		display: flex;
		flex-direction: column;
		gap: 2rem;
		flex-shrink: 0;
	}

	header h1 {
		font-size: 2.5rem;
		background: linear-gradient(135deg, var(--color-text-main), var(--color-primary));
		-webkit-background-clip: text;
		background-clip: text;
		-webkit-text-fill-color: transparent;
		margin-bottom: 0.25rem;
	}

	header p {
		color: var(--color-text-muted);
		font-size: 0.9rem;
		text-transform: uppercase;
		letter-spacing: 1px;
	}

	.controls {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 2rem;
		padding-right: 0.5rem;
	}

	.control-group h3 {
		font-size: 1rem;
		color: var(--color-text-muted);
		margin-bottom: 1rem;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0.5rem;
	}

	.btn-primary {
		width: 100%;
		font-size: 1.1rem;
	}

	.btn-export {
		width: 100%;
		background: transparent;
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		padding: 0.75rem;
		border-radius: var(--radius-sm);
		transition: all 0.2s ease;
	}

	.btn-export:hover {
		color: var(--color-text-main);
		border-color: var(--color-text-muted);
		background: rgba(255, 255, 255, 0.05);
	}

	.canvas {
		flex: 1;
		background: var(--color-bg-surface);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		overflow: hidden;
	}

	.placeholder-map {
		text-align: center;
		opacity: 0.5;
	}

	.placeholder-map h2 {
		font-size: 3rem;
		color: var(--color-text-muted);
		margin-bottom: 1rem;
	}

	.pulsing {
		animation: pulse 2s infinite ease-in-out;
		color: var(--color-primary) !important;
	}
	
	.input-group {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin-bottom: 1rem;
	}

	.input-group label {
		font-size: 0.85rem;
		color: var(--color-text-muted);
		cursor: help;
	}

	.input-group input {
		background: rgba(0, 0, 0, 0.3);
		border: 1px solid var(--color-border);
		color: var(--color-text-main);
		padding: 0.5rem;
		border-radius: var(--radius-sm);
		font-family: monospace;
	}

	.success-text {
		color: #10b981;
		font-size: 0.85rem;
		margin-top: 0.5rem;
		text-align: center;
	}

	.btn-secondary {
		width: 100%;
		background: rgba(255, 255, 255, 0.1);
		color: white;
		padding: 0.75rem 1.5rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border);
		transition: all 0.2s ease;
	}

	.btn-secondary:hover {
		background: rgba(255, 255, 255, 0.2);
	}
	
	@keyframes pulse {
		0% { opacity: 0.5; }
		50% { opacity: 1; text-shadow: 0 0 20px var(--color-primary-glow); }
		100% { opacity: 0.5; }
	}
	
	.results-container {
		display: flex;
		flex-direction: column;
		gap: 2rem;
		width: 100%;
	}
	
	.topology-map {
		text-align: center;
		padding: 2rem;
	}

	.topology-nodes {
		display: flex;
		justify-content: center;
		gap: 2rem;
		margin: 1.5rem 0;
	}

	.t-node {
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid var(--color-primary);
		padding: 1rem 2rem;
		border-radius: var(--radius-lg);
		font-weight: bold;
		box-shadow: 0 0 15px var(--color-primary-glow);
	}

	.topology-edges {
		display: flex;
		justify-content: center;
		gap: 1.5rem;
		color: var(--color-text-muted);
		font-family: monospace;
	}

	.export-actions {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}
	
	.results-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
		gap: 2rem;
		width: 100%;
	}
	
	.branch-card h3 {
		font-size: 1.5rem;
		color: var(--color-text-main);
	}
	
	.year {
		color: var(--color-primary);
		font-weight: bold;
		margin-bottom: 1rem;
	}
	
	.btn-export-small {
		background: rgba(255, 255, 255, 0.1);
		color: white;
		padding: 0.5rem 1rem;
		border-radius: var(--radius-sm);
		font-size: 0.85rem;
		margin-bottom: 1rem;
	}
	
	.btn-export-small:hover {
		background: var(--color-primary);
	}
	
	.lexicon-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	
	.lexicon-table th {
		text-align: left;
		padding: 0.5rem;
		border-bottom: 1px solid var(--color-border);
		color: var(--color-text-muted);
	}
	
	.lexicon-table td {
		padding: 0.5rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.05);
	}
	
	.ipa {
		font-family: var(--font-serif);
		font-size: 1.1rem;
		color: var(--color-accent);
	}
	
	.polysemy {
		color: var(--color-text-muted);
		font-style: italic;
	}
</style>
