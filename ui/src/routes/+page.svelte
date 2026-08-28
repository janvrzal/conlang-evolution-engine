<script lang="ts">
	import { resetApiBase, simulate } from '$lib/api';

	let simulationResult = $state<any>(null);
	let isLoading = $state(false);
	let errorMessage = $state<string | null>(null);

	async function runSimulation() {
		isLoading = true;
		errorMessage = null;
		try {
			const data = await simulate({
				topology: 'scenario_split.yaml',
				proto_csv: 'fantasy_v1.csv',
				preset: 'src/cee/data/presets/fantasy_preset.yaml',
				semantics: 'src/cee/data/semantics_mock.yaml'
			});

			if (data.status === 'success') {
				simulationResult = data;
			} else {
				errorMessage = `Engine vrátil stav '${data.status}'.`;
			}
		} catch (e) {
			// Adresu zahodíme, ať se příští pokus zkusí připojit znovu — backend
			// mohl mezitím naskočit na jiném portu.
			resetApiBase();
			errorMessage = e instanceof Error ? e.message : String(e);
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
			<p>Conlang Evolution Engine</p>
		</header>
		
		<div class="controls scroll-y">
			<section class="control-group">
				<h3>Simulace</h3>
				<button class="btn-primary" onclick={runSimulation} disabled={isLoading}>
					{isLoading ? 'Simuluji vesmír...' : 'Spustit Vývoj'}
				</button>

				{#if errorMessage}
					<p class="error-box">{errorMessage}</p>
				{/if}
			</section>
			
			<section class="control-group">
				<h3>Jazyky</h3>
				<div class="language-list">
					<div class="lang-item active">Proto-jazyk</div>
					<div class="lang-item">Severní větev</div>
					<div class="lang-item">Jižní větev</div>
				</div>
			</section>
		</div>
		
		<footer>
			<button class="btn-export">Export Dat</button>
		</footer>
	</aside>

	<!-- Hlavní plátno: Mapa / Strom -->
	<main class="canvas scroll-y" style="align-items: flex-start; justify-content: flex-start; padding: 2rem;">
		{#if !simulationResult && !isLoading}
			<div class="placeholder-map" style="margin: auto;">
				<h2>Evoluční Mapa</h2>
				<p>Zde bude interaktivní zobrazení stromu jazyků a vizuální mapa světa.</p>
			</div>
		{:else if isLoading}
			<div class="placeholder-map" style="margin: auto;">
				<h2 class="pulsing">Evoluce probíhá...</h2>
				<p>Kalkuluji fonologické pravidla a sémantické posuny</p>
			</div>
		{:else}
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
					{#each Object.entries(simulationResult.branches) as [branchId, branchData]}
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

	.language-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.lang-item {
		padding: 0.75rem 1rem;
		background: rgba(0, 0, 0, 0.2);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.lang-item:hover {
		background: rgba(255, 255, 255, 0.05);
	}

	.lang-item.active {
		border-color: var(--color-primary);
		box-shadow: 0 0 10px var(--color-primary-glow);
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
