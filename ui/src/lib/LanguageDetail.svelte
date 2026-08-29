<script lang="ts">
	import { fetchLanguage, fetchWordTrace, resetApiBase } from '$lib/api';
	import { X, Loader2, ArrowRight, Map } from 'lucide-svelte';
	import { t } from '$lib/i18n.svelte';

	type TraceStep = { year: number; form: string; rule_name: string | null; type: string | null; note: string | null };
	type WordNode = { id: string, concept_id: string, from: string, to: string, polysemy: string[] };

	let {
		runId = null,
		nodeId,
		label,
		biome = null,
		years = 1000,
		currentYear,
		embedded = false,
		onclose,
		onIsogloss
	} = $props<{
		runId?: string | null;
		nodeId: string;
		label: string;
		biome?: string | null;
		years?: number;
		currentYear: number;
		embedded?: boolean;
		onclose: () => void;
		onIsogloss?: (conceptId: string) => void;
	}>();

	let loading = $state(false);
	let error = $state<string | null>(null);
	let words = $state<WordNode[]>([]);
	let traces = $state<Record<string, TraceStep[]>>({});
	let openWordId = $state<string | null>(null);

	let searchQuery = $state('');

	let filteredWords = $derived(
		words.filter(w => {
			if (!searchQuery) return true;
			const q = searchQuery.toLowerCase();
			return w.to.toLowerCase().includes(q) 
				|| w.concept_id.toLowerCase().includes(q)
				|| w.polysemy.some(p => p.toLowerCase().includes(q));
		})
	);

	// Znovu načteme pokaždé, když se změní uzel nebo aktuální rok na ose.
	$effect(() => {
		if (runId) void load(runId, nodeId, currentYear);
		else {
			words = [];
			traces = {};
			error = null;
		}
	});

	async function load(simulationRunId: string, id: string, year?: number) {
		loading = true;
		error = null;
		try {
			const fetched = await fetchLanguage(simulationRunId, id, year);
			console.log(`Načteno slov pro ${id}:`, fetched.length);
			
			// Skryjeme vizuální duplicity (slova se stejným konceptem a stejným finálním zněním),
			// aby se uživateli nezapleveloval slovník.
			const uniqueWords = [];
			const seen = new Set();
			for (const w of fetched) {
				const key = w.concept_id + '|' + w.to;
				if (!seen.has(key)) {
					seen.add(key);
					uniqueWords.push(w);
				}
			}
			
			words = uniqueWords;
			traces = {};
			openWordId = null;
		} catch (e) {
			console.error("Chyba při načítání:", e);
			resetApiBase();
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function toggle(wordId: string) {
		if (openWordId === wordId) {
			openWordId = null;
			return;
		}
		openWordId = wordId;
		if (!traces[wordId]) {
			try {
				if (runId) traces[wordId] = await fetchWordTrace(runId, wordId);
			} catch (e) {
				console.error(e);
			}
		}
	}
</script>

<aside class:embedded class="detail">
	<header>
		<div>
			<h2>{label}</h2>
			<p class="sub">
				{#if biome}<span class="tag">{biome}</span>{/if}
				<span>{t('stateInYear')} {currentYear}</span>
				<span>{years} let vývoje</span>
			</p>
		</div>
		<button class="icon" onclick={onclose} aria-label="Zavřít panel"><X size={16} /></button>
	</header>

	{#if loading}
		<div class="state"><Loader2 size={18} class="spin" /> {t('loading')}</div>
	{:else if error}
		<div class="state error">{error}</div>
	{:else if !runId}
		<div class="state text-center text-muted-foreground p-8">{t('lexiconUnavailable')}</div>
	{:else if !words.length}
		<div class="state text-center text-muted-foreground p-8">V tomto roce jazyk ještě nemá žádná slova.</div>
	{:else}
		<section class="flex-1 flex flex-col min-h-0">
			<div class="px-4 pb-3 pt-1 sticky top-0 bg-card z-10 border-b border-border/40">
				<div class="flex items-center justify-between mb-3">
					<h3 class="m-0 text-xs font-semibold tracking-wider uppercase opacity-60">{t('lexicon')} <span class="ml-1 opacity-70 font-normal">{filteredWords.length} / {words.length}</span></h3>
				</div>
				<div class="relative">
					<input 
						type="text" 
						class="w-full h-8 px-3 text-sm bg-muted/50 border border-border/50 rounded-md focus:outline-none focus:ring-1 focus:ring-primary focus:bg-background transition-all placeholder:text-muted-foreground" 
						placeholder={t('searchWord')}
						bind:value={searchQuery}
					/>
					{#if searchQuery}
						<button class="absolute right-2 top-1.5 text-muted-foreground hover:text-foreground" onclick={() => searchQuery = ''}>
							<X size={14} />
						</button>
					{/if}
				</div>
			</div>
			
			<ul class="words flex-1 overflow-y-auto">
				{#each [...filteredWords].sort((a, b) => a.to.localeCompare(b.to)) as word (word.id)}
					<li class="border-b border-border/40 last:border-0 {word.from !== word.to ? 'changed' : ''}">
						<div class="word-container flex justify-between items-start p-3 hover:bg-muted/30 transition-colors">
							<button class="flex-1 text-left" onclick={() => toggle(word.id)}>
								<div class="flex items-baseline gap-2 mb-1">
									<strong class="text-base font-medium">{word.to}</strong>
									{#if word.from !== word.to}
										<span class="text-xs text-muted-foreground flex items-center gap-1">
											(z <i class="opacity-80">{word.from}</i>)
										</span>
									{/if}
								</div>
								
								<div class="text-sm text-muted-foreground mb-1 font-serif italic">
									"{word.concept_id}"
								</div>
								
								{#if word.polysemy?.length}
									<div class="polysemy-tags flex flex-wrap gap-1 mt-1.5">
										{#each word.polysemy as meaning}
											<span class="poly-tag px-1.5 py-0.5 text-[10px] rounded bg-primary/10 text-primary font-medium">{meaning}</span>
										{/each}
									</div>
								{/if}
							</button>
							
							{#if onIsogloss}
								<button 
									class="p-1.5 mt-1 text-muted-foreground hover:text-primary hover:bg-muted rounded-md transition-colors shrink-0"
									title="Zobrazit izoglosu na mapě"
									onclick={(e) => { e.stopPropagation(); onIsogloss(word.concept_id); }}>
									<Map size={15} />
								</button>
							{/if}
						</div>
						
						{#if openWordId === word.id && traces[word.id]}
							<div class="px-3 pb-3 pt-1">
								<ol class="trace">
									{#each traces[word.id] as step, i (i)}
										<li>
											<span class="year w-10 shrink-0 text-xs text-muted-foreground">{step.year}</span>
											<div class="step-info flex-1">
												{#if step.type === 'borrowed'}
													<span class="rule text-amber-600 font-medium">Výpůjčka</span>
												{:else if step.rule_name}
													<span class="rule font-medium">{step.rule_name}</span>
												{:else if step.note}
													<span class="rule italic text-muted-foreground">{step.note}</span>
												{/if}
											</div>
											<b class="form font-medium shrink-0">{step.form}</b>
										</li>
										<li class="empty-step text-muted-foreground italic text-xs py-1">Tvar se nezměnil.</li>
									{/each}
								</ol>
							</div>
						{/if}
					</li>
				{/each}
				{#if filteredWords.length === 0}
					<div class="text-center p-8 text-muted-foreground text-sm">
						Nic nenalezeno.
					</div>
				{/if}
			</ul>
		</section>
	{/if}
</aside>

<style>
	.detail {
		width: 380px;
		height: 100%;
		display: flex;
		flex-direction: column;
		gap: 4px;
		overflow-y: auto;
		background: hsl(var(--card, 0 0% 100%));
		border-left: 1px solid hsl(var(--border, 0 0% 90%));
		font-size: 13px;
	}

	.detail.embedded {
		width: 100%;
		height: min(56vh, 560px);
		border: 1px solid hsl(var(--border, 0 0% 90%));
		border-radius: 0.5rem;
	}

	header {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		padding: 16px;
		background: inherit;
		border-bottom: 1px solid hsl(var(--border, 0 0% 90%));
	}

	h2 {
		margin: 0;
		font-size: 15px;
		font-weight: 600;
	}

	.sub {
		margin: 4px 0 0;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 11px;
		opacity: 0.65;
	}

	.tag {
		padding: 1px 6px;
		border-radius: 999px;
		border: 1px solid hsl(var(--border, 0 0% 90%));
	}

	.icon {
		display: grid;
		place-items: center;
		width: 26px;
		height: 26px;
		border-radius: 6px;
		border: none;
		background: transparent;
		cursor: pointer;
		opacity: 0.6;
	}

	.icon:hover {
		opacity: 1;
		background: hsl(var(--muted, 0 0% 96%));
	}

	.state {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 24px 16px;
		opacity: 0.7;
	}

	.state.error {
		color: #dc2626;
		opacity: 1;
	}

	:global(.spin) {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.trace {
		list-style: none;
		margin: 2px 0 10px;
		padding: 8px 10px;
		border-left: 2px solid #6b7cff;
		background: hsl(var(--muted, 0 0% 96%) / 0.6);
		border-radius: 0 5px 5px 0;
		display: flex;
		flex-direction: column;
		gap: 5px;
		font-size: 11px;
	}

	.trace li {
		display: grid;
		grid-template-columns: 38px 70px 1fr;
		gap: 8px;
		align-items: baseline;
	}
</style>
