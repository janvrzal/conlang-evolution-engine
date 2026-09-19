<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import {
		ArrowLeft,
		BookOpen,
		CalendarDays,
		GitBranch,
		History,
		LayoutDashboard,
		Plus,
		Save,
		Settings,
		Users
	} from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Label } from '$lib/components/ui/label';
	import { Select } from '$lib/components/ui/select';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import LanguageLexicon, { type LanguageWord } from '$lib/LanguageLexicon.svelte';
	import { fetchRunExport, fetchWordTrace } from '$lib/api';
	import { fetchLanguagePage, type LexiconFilters } from '$lib/language-api';
	import {
		loadProject,
		projectState,
		scheduleSave,
		type HomophonyStrategy
	} from '$lib/state.svelte';

	type AuthorEvent = { id: string; year: number; type: string; note: string; varietyId?: string };
	type AuditEvent = Record<string, unknown> & {
		kind?: string;
		year?: number;
		language_id?: string;
	};
	type PendingHomophony = AuditEvent & {
		decision_id: string;
		winner_id?: string;
		loser_id?: string;
		pressure?: number;
		reason?: string;
	};

	let ready = $state(false);
	let selectedYear = $state(0);
	let selectedYearOption = $state('0');
	let words = $state<LanguageWord[]>([]);
	let auditEvents = $state<AuditEvent[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let labelDraft = $state('');
	let endonymDraft = $state('');
	let exonymDraft = $state('');
	let nameAutonomyDraft = $state(0.5);
	let namePoolDraft = $state('');
	let eventType = $state('metadata');
	let eventNote = $state('');
	let selectedTrace = $state<{ word: LanguageWord; steps: any[] } | null>(null);
	let activeView = $state<
		'overview' | 'lexicon' | 'timeline' | 'varieties' | 'settings' | 'catalog'
	>('overview');
	let lexiconFilters = $state<LexiconFilters>({
		query: '',
		register: 'all',
		community: 'all',
		lexicalClass: 'all'
	});
	let lexiconTotal = $state(0);
	let lexiconNextOffset = $state<number | null>(null);
	let lexiconFacets = $state({
		registers: [] as string[],
		communities: [] as string[],
		lexicalClasses: [] as string[],
		homonymForms: [] as string[],
		synonymConcepts: [] as string[]
	});
	let filterTimer: ReturnType<typeof setTimeout> | null = null;
	let lastHistoricalLoad = $state('');
	let resolutionKind = $state<HomophonyStrategy['kind']>('colexification');
	let resolutionSource = $state('');
	let resolutionAffix = $state('');
	let resolutionModifier = $state('');

	const languageId = $derived($page.params.languageId);
	const projectId = $derived($page.params.id);
	const years = $derived([...projectState.timeSteps].sort((a, b) => a - b));
	const activeSnapshot = $derived.by(() => {
		const year = [...years].filter((item) => item <= selectedYear).at(-1) ?? years[0] ?? 0;
		return projectState.snapshots[year] ?? { nodes: [], edges: [] };
	});
	const languageNode = $derived(
		activeSnapshot.nodes.find((node: any) => node.id === languageId) ?? null
	);
	const languageData = $derived((languageNode?.data ?? {}) as Record<string, any>);
	const authorEvents = $derived((languageData.languageEvents ?? []) as AuthorEvent[]);
	const visibleEvents = $derived(
		[
			...auditEvents.filter((event) => Number(event.year ?? 0) <= selectedYear),
			...authorEvents
				.filter((event) => event.year <= selectedYear)
				.map((event) => ({ ...event, kind: `author:${event.type}` }))
		].sort((left, right) => Number(right.year ?? 0) - Number(left.year ?? 0)) as AuditEvent[]
	);
	const requestedHomophonyId = $derived($page.url.searchParams.get('homophony'));
	const pendingHomophony = $derived.by(
		() =>
			auditEvents.find(
				(event): event is PendingHomophony =>
					event.kind === 'homophony_pending' && event.decision_id === requestedHomophonyId
			) ?? null
	);
	const pendingSemanticProposals = $derived(
		auditEvents.filter(
			(event) =>
				event.kind === 'semantic_proposal' &&
				event.status === 'pending' &&
				Number(event.year ?? 0) <= selectedYear
		)
	);
	const historicalEffectsAtYear = $derived(
		auditEvents
			.filter(
				(event) => event.kind === 'historical_event' && Number(event.year ?? 0) === selectedYear
			)
			.flatMap((event) =>
				Array.isArray(event.effects)
					? event.effects.map((effect: any) => ({
							...effect,
							eventKind: event.event_kind,
							phase: event.phase
						}))
					: []
			)
	);
	const homophonyLoser = $derived(
		pendingHomophony?.loser_id
			? (words.find((word) => word.id === pendingHomophony?.loser_id) ?? null)
			: null
	);
	const homophonyWinner = $derived(
		pendingHomophony?.winner_id
			? (words.find((word) => word.id === pendingHomophony?.winner_id) ?? null)
			: null
	);
	const communities = $derived(
		Array.isArray(languageData.communities) ? languageData.communities : []
	);
	const varieties = $derived.by(() => {
		const configured = Array.isArray(languageData.communities) ? languageData.communities : [];
		const fromAudit = auditEvents
			.filter(
				(event) => event.kind === 'variety_divergence' || event.kind === 'language_split_candidate'
			)
			.map((event) => ({
				id: String(event.variety_id ?? event.community_id),
				divergence: event.divergence,
				candidate: event.kind === 'language_split_candidate'
			}));
		return [
			...configured.map((item: any) => ({ id: item.variety_id ?? item.id, ...item })),
			...fromAudit
		].filter(
			(item, index, all) =>
				item.id && all.findIndex((candidate) => candidate.id === item.id) === index
		);
	});
	const catalog = $derived.by(() => {
		const known: Map<string, { id: string; label: string; year: number }> = new Map();
		for (const year of years)
			for (const node of projectState.snapshots[year]?.nodes ?? []) {
				if (!known.has(node.id))
					known.set(node.id, { id: node.id, label: node.data?.label ?? node.id, year });
			}
		return [...known.values()].sort(
			(left, right) => left.year - right.year || left.label.localeCompare(right.label)
		);
	});
	const views = [
		{ id: 'overview' as const, label: 'Přehled', icon: LayoutDashboard },
		{ id: 'lexicon' as const, label: 'Slovník', icon: BookOpen },
		{ id: 'timeline' as const, label: 'Časová osa', icon: History },
		{ id: 'varieties' as const, label: 'Variety', icon: GitBranch },
		{ id: 'settings' as const, label: 'Nastavení', icon: Settings },
		{ id: 'catalog' as const, label: 'Jazyky projektu', icon: Users }
	];

	onMount(() => {
		void (async () => {
			await loadProject(projectId ?? 'default');
			selectedYear = Number(
				$page.url.searchParams.get('year') ?? projectState.timeSteps.at(-1) ?? 0
			);
			selectedYearOption = String(selectedYear);
			// Z fronty homofonií se otevírá přímo audit daného jazyka a roku.
			if ($page.url.searchParams.has('homophony')) activeView = 'timeline';
			labelDraft = String(languageData.label ?? languageId);
			endonymDraft = String(languageData.endonym ?? languageData.label ?? languageId);
			exonymDraft = String(languageData.exonym ?? languageData.label ?? languageId);
			nameAutonomyDraft = Number(languageData.nameAutonomy ?? 0.5);
			namePoolDraft = Array.isArray(languageData.namePool) ? languageData.namePool.join(', ') : '';
			ready = true;
		})();
	});

	$effect(() => {
		if (!ready) return;
		labelDraft = String(languageData.label ?? languageId);
		endonymDraft = String(languageData.endonym ?? languageData.label ?? languageId);
		exonymDraft = String(languageData.exonym ?? languageData.label ?? languageId);
		nameAutonomyDraft = Number(languageData.nameAutonomy ?? 0.5);
		namePoolDraft = Array.isArray(languageData.namePool) ? languageData.namePool.join(', ') : '';
	});

	$effect(() => {
		if (!ready) return;
		const loadKey = `${projectState.simulationRunId ?? ''}:${languageId ?? ''}:${selectedYear}`;
		if (loadKey === lastHistoricalLoad) return;
		lastHistoricalLoad = loadKey;
		void loadHistoricalState();
	});

	function setYear(value: string) {
		selectedYear = Number(value);
		selectedYearOption = value;
	}

	async function loadHistoricalState() {
		if (!projectState.simulationRunId) {
			words = [];
			auditEvents = [];
			lexiconTotal = 0;
			return;
		}
		loading = true;
		error = null;
		try {
			await loadLexiconPage(0);
			const exported = await fetchRunExport(projectState.simulationRunId);
			auditEvents = (exported.events ?? []).filter(
				(event: AuditEvent) => event.language_id === languageId
			);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			loading = false;
		}
	}

	async function loadLexiconPage(offset: number, append = false) {
		if (!projectState.simulationRunId) return;
		const result = await fetchLanguagePage(
			projectState.simulationRunId,
			languageId ?? '',
			selectedYear,
			offset,
			lexiconFilters
		);
		words = append ? [...words, ...result.words] : result.words;
		lexiconTotal = result.total;
		lexiconNextOffset = result.nextOffset;
		lexiconFacets = result.facets;
	}
	function updateLexiconFilters(filters: LexiconFilters) {
		lexiconFilters = filters;
		if (filterTimer) clearTimeout(filterTimer);
		filterTimer = setTimeout(() => {
			void loadLexiconPage(0);
		}, 220);
	}

	function updateLanguageData(update: Record<string, unknown>) {
		projectState.snapshots = Object.fromEntries(
			Object.entries(projectState.snapshots).map(([year, snapshot]) => {
				if (Number(year) < selectedYear) return [year, snapshot];
				return [
					year,
					{
						...snapshot,
						nodes: snapshot.nodes.map((node: any) =>
							node.id === languageId ? { ...node, data: { ...node.data, ...update } } : node
						)
					}
				];
			})
		);
		scheduleSave();
	}

	function saveName() {
		const namePool = namePoolDraft
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
		updateLanguageData({
			label: labelDraft,
			endonym: endonymDraft || labelDraft,
			exonym: exonymDraft || labelDraft,
			nameAutonomy: nameAutonomyDraft,
			namePool
		});
		addAuthorEvent('metadata', `Název jazyka: ${labelDraft}`);
	}
	function addAuthorEvent(type = eventType, note = eventNote, varietyId?: string) {
		const item: AuthorEvent = {
			id: `language-event-${Date.now()}`,
			year: selectedYear,
			type,
			note: note || type,
			varietyId
		};
		updateLanguageData({ languageEvents: [...authorEvents, item] });
		eventNote = '';
	}
	function approveSemanticProposal(proposal: AuditEvent) {
		const key = String(proposal.proposal_key ?? '');
		if (!key) return;
		const semantic = { ...(languageData.semantic ?? {}) };
		const approved = new Set<string>(
			Array.isArray(semantic.approved_changes) ? semantic.approved_changes : []
		);
		approved.add(key);
		updateLanguageData({
			semantic: { ...semantic, approval_mode: 'review', approved_changes: [...approved] }
		});
		addAuthorEvent('semantic:approve', `Schválen sémantický návrh ${key}.`);
	}
	function confirmHomophonyResolution() {
		if (!pendingHomophony || !homophonyLoser) return;
		let strategy: HomophonyStrategy;
		if (resolutionKind === 'colexification') strategy = { kind: 'colexification' };
		else if (resolutionKind === 'semantic_shift') {
			if (!resolutionSource) return;
			strategy = { kind: 'semantic_shift', source: resolutionSource };
		} else if (resolutionKind === 'derivation') {
			if (!resolutionSource || !resolutionAffix) return;
			strategy = { kind: 'derivation', root: resolutionSource, affix: resolutionAffix };
		} else {
			if (!resolutionSource || !resolutionModifier) return;
			strategy = { kind: 'compound', head: resolutionSource, modifier: resolutionModifier };
		}
		const lexical = { ...(languageData.lexical ?? {}) };
		const strategies = {
			...(lexical.homophony_strategies ?? {}),
			[homophonyLoser.concept_id]: strategy
		};
		updateLanguageData({
			lexical: {
				...lexical,
				enabled: true,
				homophony_policy: 'resolve',
				homophony_strategies: strategies
			}
		});
		projectState.homophonyQueue = {
			...projectState.homophonyQueue,
			[pendingHomophony.decision_id]: {
				status: 'resolved',
				year: selectedYear,
				strategy,
				loserConcept: homophonyLoser.concept_id
			}
		};
		addAuthorEvent(
			'homophony:resolve',
			`Řešení homofonie ${homophonyLoser.concept_id}: ${strategy.kind}.`
		);
		scheduleSave();
	}
	function updateSemantic(update: Record<string, unknown>) {
		updateLanguageData({ semantic: { ...(languageData.semantic ?? {}), ...update } });
	}
	function updatePressures(update: Record<string, number>) {
		updateSemantic({ pressures: { ...(languageData.semantic?.pressures ?? {}), ...update } });
	}
	function updateRegisters(update: Record<string, number>) {
		updateSemantic({ registers: { ...(languageData.semantic?.registers ?? {}), ...update } });
	}
	function updateCommunities(next: any[]) {
		updateLanguageData({ communities: next });
	}
	function addCommunity() {
		const id = `community-${communities.length + 1}`;
		updateCommunities([
			...communities,
			{
				id,
				share: 0.1,
				prestige: 0.5,
				mobility: 0.5,
				urbanity: 0.5,
				generation: 'mixed',
				kind: 'social',
				domains: [],
				links: {},
				variety_id: `variety:${id}`
			}
		]);
	}
	function patchCommunity(id: string, update: Record<string, unknown>) {
		updateCommunities(
			communities.map((community: any) =>
				community.id === id ? { ...community, ...update } : community
			)
		);
	}
	function removeCommunity(id: string) {
		updateCommunities(
			communities
				.filter((community: any) => community.id !== id)
				.map((community: any) => ({
					...community,
					links: Object.fromEntries(
						Object.entries(community.links ?? {}).filter(([target]) => target !== id)
					)
				}))
		);
	}
	function recordSocialChange(changes: Record<string, unknown>, note: string) {
		const history = Array.isArray(languageData.social_history) ? languageData.social_history : [];
		updateLanguageData({ social_history: [...history, { year: selectedYear, changes }] });
		addAuthorEvent('social', note);
	}
	function decideVariety(varietyId: string, action: string) {
		if (action === 'split') {
			spawnLanguageFromVariety(varietyId);
			return;
		}
		const communities = (
			Array.isArray(languageData.communities) ? languageData.communities : []
		).map((item: any) =>
			(item.variety_id ?? item.id) === varietyId ? { ...item, status: action } : item
		);
		const history = Array.isArray(languageData.social_history) ? languageData.social_history : [];
		updateLanguageData({
			communities,
			social_history: [
				...history,
				{
					year: selectedYear,
					changes: { variety_action: { variety_id: varietyId, action } }
				}
			]
		});
		addAuthorEvent(
			`variety:${action}`,
			`Rozhodnutí pro varietu ${varietyId}: ${action}`,
			varietyId
		);
	}
	function spawnLanguageFromVariety(varietyId: string) {
		if (!languageNode) return;
		const newId = `lang-${Date.now()}`;
		const names = Array.isArray(languageData.namePool)
			? languageData.namePool.filter((item: unknown) => typeof item === 'string' && item.trim())
			: [];
		const endonym = String(
			names.find((name: string) => name !== languageData.endonym) ??
				`${String(languageData.endonym ?? languageData.label ?? languageId)} — ${varietyId}`
		);
		const exonym =
			Number(languageData.nameAutonomy ?? 0.5) >= 0.5
				? endonym
				: `${String(languageData.exonym ?? languageData.label ?? languageId)} (${varietyId})`;
		const label = endonym;
		projectState.snapshots = Object.fromEntries(
			Object.entries(projectState.snapshots).map(([year, snapshot]) => {
				if (Number(year) < selectedYear) return [year, snapshot];
				if (snapshot.nodes.some((node: any) => node.id === newId)) return [year, snapshot];
				const child = {
					...languageNode,
					id: newId,
					position: {
						x: Number(languageNode.position?.x ?? 0) + 230,
						y: Number(languageNode.position?.y ?? 0) + 130
					},
					data: {
						...languageData,
						label,
						endonym,
						exonym,
						year: selectedYear,
						isProto: false,
						originVariety: varietyId,
						communities: communities.filter(
							(community: any) => (community.variety_id ?? community.id) === varietyId
						),
						languageEvents: []
					}
				};
				const edge = {
					id: `inheritance-${languageId}-${newId}`,
					source: languageId,
					target: newId,
					type: 'inheritance',
					data: { kind: 'inheritance', year: selectedYear }
				};
				return [
					year,
					{ ...snapshot, nodes: [...snapshot.nodes, child], edges: [...snapshot.edges, edge] }
				];
			})
		);
		addAuthorEvent(
			'variety:split',
			`Vznikl nový jazyk ${label} z variety ${varietyId}.`,
			varietyId
		);
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
			<div class="space-y-2">
				<Button href={`/project/${projectId}/map`} variant="ghost" size="sm"
					><ArrowLeft /> Na mapu</Button
				>
				<div class="flex items-center gap-3">
					<div class="rounded-lg bg-primary/10 p-3 text-primary"><BookOpen size={24} /></div>
					<div>
						<p class="text-sm text-muted-foreground">Správa jazyka</p>
						<h1 class="text-3xl font-semibold tracking-tight">
							{languageData.label ?? languageId}
						</h1>
						<p class="text-sm text-muted-foreground">
							Stav v roce {selectedYear} · {words.length} živých lexémů
						</p>
					</div>
				</div>
			</div>
			<div class="flex items-center gap-2">
				<CalendarDays size={17} class="text-muted-foreground" /><Select
					class="w-40"
					value={selectedYearOption}
					onchange={(event) => setYear(event.currentTarget.value)}
					>{#each years as year}<option value={String(year)}>{year}. rok</option>{/each}</Select
				>
			</div>
		</header>

		{#if !languageNode}<Card
				><CardContent class="p-8 text-muted-foreground"
					>Jazyk v tomto roce ještě neexistuje. Zvol dřívější rok nebo se vrať na mapu.</CardContent
				></Card
			>
		{:else}
			<div class="grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
				<aside class="lg:sticky lg:top-6 lg:self-start">
					<Card class="overflow-visible">
						<CardHeader class="pb-3"
							><CardTitle class="text-base">Pracovní pohledy</CardTitle><CardDescription
								>Každý pohled pracuje se stejným stavem v roce {selectedYear}.</CardDescription
							></CardHeader
						>
						<CardContent class="space-y-1">
							{#each views as view}
								{@const Icon = view.icon}
								<Button
									variant={activeView === view.id ? 'secondary' : 'ghost'}
									class="w-full justify-start"
									onclick={() => (activeView = view.id)}><Icon /> {view.label}</Button
								>
							{/each}
						</CardContent>
					</Card>
				</aside>
				<section class="min-w-0 space-y-6">
					{#if error}<Card class="border-destructive"
							><CardContent class="p-4 text-destructive">{error}</CardContent></Card
						>{/if}
					{#if activeView === 'overview'}
						<div class="grid gap-4 md:grid-cols-3">
							<Card
								><CardHeader
									><CardDescription>Živé lexémy</CardDescription><CardTitle class="text-3xl"
										>{words.length}</CardTitle
									></CardHeader
								></Card
							><Card
								><CardHeader
									><CardDescription>Variety</CardDescription><CardTitle class="text-3xl"
										>{varieties.length}</CardTitle
									></CardHeader
								></Card
							><Card
								><CardHeader
									><CardDescription>Události do roku</CardDescription><CardTitle class="text-3xl"
										>{visibleEvents.length}</CardTitle
									></CardHeader
								></Card
							>
						</div>
						{#if historicalEffectsAtYear.length}<Card
								><CardHeader
									><CardTitle>Historické účinky v roce {selectedYear}</CardTitle><CardDescription
										>Každý řádek ukazuje, proč se konkrétní sociální parametr změnil.</CardDescription
									></CardHeader
								><CardContent class="space-y-2"
									>{#each historicalEffectsAtYear as effect, index (`effect-${effect.source_event_id}-${effect.parameter}-${index}`)}<div
											class="grid grid-cols-[1fr_auto] gap-2 border-b pb-2 text-sm last:border-0"
										>
											<div>
												<strong>{String(effect.parameter)}</strong><span
													class="ml-2 text-muted-foreground"
													>{String(effect.eventKind)} · {String(effect.curve)} · {Math.round(
														Number(effect.strength ?? 0) * 100
													)} %</span
												>
											</div>
											<span
												>{Number(effect.before ?? 0).toFixed(2)} → {Number(
													effect.after ?? 0
												).toFixed(2)}</span
											>
										</div>{/each}</CardContent
								></Card
							>{/if}
						<Card
							><CardHeader
								><CardTitle>Co je důležité v tomto okamžiku</CardTitle><CardDescription
									>Nejnovější změny a otevřené možnosti pro worldbuildera.</CardDescription
								></CardHeader
							><CardContent class="space-y-3"
								>{#each visibleEvents.slice(0, 5) as event, index (`overview-${event.kind}-${event.year}-${index}`)}<div
										class="flex gap-3 border-b pb-3 last:border-0"
									>
										<span class="w-14 text-sm text-muted-foreground">{event.year}</span>
										<div>
											<strong class="text-sm">{String(event.kind ?? event.type)}</strong>
											<p class="text-sm text-muted-foreground">
												{String(event.note ?? event.reason ?? event.rule ?? 'Historická událost')}
											</p>
										</div>
									</div>{:else}<p class="text-sm text-muted-foreground">
										Ještě nejsou k dispozici auditní události. Spusť simulaci nebo přidej autorskou
										událost.
									</p>{/each}</CardContent
							></Card
						>
					{:else if activeView === 'lexicon'}
						{#if loading}<Card
								><CardContent class="p-8 text-muted-foreground"
									>Načítám historický stav jazyka…</CardContent
								></Card
							>{:else}<LanguageLexicon
								{words}
								total={lexiconTotal}
								facets={lexiconFacets}
								filters={lexiconFilters}
								onFiltersChange={updateLexiconFilters}
								hasMore={lexiconNextOffset !== null}
								onLoadMore={() =>
									lexiconNextOffset !== null && loadLexiconPage(lexiconNextOffset, true)}
								onTrace={showTrace}
							/>{/if}
						{#if selectedTrace}<Card
								><CardHeader
									><CardTitle>Historie: {selectedTrace.word.to}</CardTitle><CardDescription
										>{selectedTrace.word.concept_id}</CardDescription
									></CardHeader
								><CardContent
									><ol class="space-y-2">
										{#each selectedTrace.steps as step}<li
												class="flex gap-3 border-b pb-2 last:border-0"
											>
												<span class="w-14 text-muted-foreground">{step.year}</span><strong
													>{step.form}</strong
												><span class="text-muted-foreground"
													>{step.rule_name ?? step.note ?? step.type ?? ''}</span
												>
											</li>{/each}
									</ol></CardContent
								></Card
							>{/if}
					{:else if activeView === 'timeline'}
						{#if pendingSemanticProposals.length}
							<Card class="border-primary/40"
								><CardHeader
									><CardTitle>Sémantické návrhy ke schválení</CardTitle><CardDescription
										>Schválení uloží konkrétní doložený posun pro další běh; hotový běh se zpětně
										nemění.</CardDescription
									></CardHeader
								><CardContent class="space-y-2"
									>{#each pendingSemanticProposals as proposal (String(proposal.proposal_key))}<div
											class="flex items-center justify-between gap-3 rounded-md border p-3"
										>
											<div class="text-sm">
												<strong>{String(proposal.source_concept)}</strong> →
												<strong>{String(proposal.target_concept)}</strong>
												<p class="text-xs text-muted-foreground">
													{String(proposal.mechanism ?? 'doložený posun')} · tlak {Math.round(
														Number(proposal.pressure ?? 0) * 100
													)} %
												</p>
											</div>
											<Button size="sm" onclick={() => approveSemanticProposal(proposal)}
												>Schválit</Button
											>
										</div>{/each}</CardContent
								></Card
							>
						{/if}
						{#if pendingHomophony}
							<Card class="border-primary/40">
								<CardHeader
									><CardTitle>Vyřešit homofonii</CardTitle><CardDescription
										>Rozhodnutí se uloží do historie projektu a použije se při příštím spuštění
										simulace. Aktuální uložený běh se tím zpětně nepřepisuje.</CardDescription
									></CardHeader
								>
								<CardContent class="space-y-4">
									<div class="rounded-md bg-muted p-3 text-sm">
										<strong>{homophonyWinner?.concept_id ?? pendingHomophony.winner_id}</strong> ↔
										<strong>{homophonyLoser?.concept_id ?? pendingHomophony.loser_id}</strong><span
											class="ml-2 text-muted-foreground"
											>tlak {Math.round(Number(pendingHomophony.pressure ?? 0) * 100)} %</span
										>
										<p class="mt-1 text-xs text-muted-foreground">{pendingHomophony.reason}</p>
									</div>
									{#if !homophonyLoser}<p class="text-sm text-destructive">
											Historický lexém pro tuto položku není v zvoleném roce k dispozici. Zvol rok
											události a zkus to znovu.
										</p>
									{:else}
										<div class="grid gap-3 md:grid-cols-2">
											<Label
												>Legitimní strategie<Select bind:value={resolutionKind}
													><option value="colexification"
														>Kolexifikace — významy zůstanou v jednom slově</option
													><option value="semantic_shift"
														>Sémantický posun existujícího slova</option
													><option value="derivation">Odvození z kořene a afixu</option><option
														value="compound">Složenina ze dvou existujících slov</option
													></Select
												></Label
											>
											{#if resolutionKind === 'semantic_shift'}<Label
													>Zdrojové slovo<Select bind:value={resolutionSource}
														><option value="">Vyber slovo…</option
														>{#each words.filter((word) => word.concept_id !== homophonyLoser?.concept_id) as word}<option
																value={word.concept_id}>{word.concept_id} · {word.to}</option
															>{/each}</Select
													></Label
												>
											{:else if resolutionKind === 'derivation'}<Label
													>Kořen<Select bind:value={resolutionSource}
														><option value="">Vyber kořen…</option
														>{#each words.filter((word) => word.concept_id !== homophonyLoser?.concept_id) as word}<option
																value={word.concept_id}>{word.concept_id} · {word.to}</option
															>{/each}</Select
													></Label
												><Label
													>Afix<Select bind:value={resolutionAffix}
														><option value="">Vyber afix…</option
														>{#each words.filter((word) => word.is_grammatical) as word}<option
																value={word.concept_id}>{word.concept_id} · {word.to}</option
															>{/each}</Select
													></Label
												>
											{:else if resolutionKind === 'compound'}<Label
													>Hlava složeniny<Select bind:value={resolutionSource}
														><option value="">Vyber slovo…</option
														>{#each words.filter((word) => word.concept_id !== homophonyLoser?.concept_id) as word}<option
																value={word.concept_id}>{word.concept_id} · {word.to}</option
															>{/each}</Select
													></Label
												><Label
													>Modifikátor<Select bind:value={resolutionModifier}
														><option value="">Vyber slovo…</option
														>{#each words.filter((word) => word.concept_id !== homophonyLoser?.concept_id) as word}<option
																value={word.concept_id}>{word.concept_id} · {word.to}</option
															>{/each}</Select
													></Label
												>{/if}
										</div>
										<Button onclick={confirmHomophonyResolution}>Potvrdit řešení</Button>
									{/if}
								</CardContent>
							</Card>
						{/if}
						<Card
							><CardHeader
								><CardTitle class="flex items-center gap-2"
									><History size={18} /> Události jazyka</CardTitle
								><CardDescription
									>Audit simulace a vlastní rozhodnutí autora pro vybraný rok.</CardDescription
								></CardHeader
							><CardContent class="space-y-3"
								>{#each visibleEvents as event, index (`${event.kind}-${event.year}-${index}`)}<div
										class="rounded-lg border p-3"
									>
										<div class="flex justify-between gap-3">
											<strong class="text-sm">{String(event.kind ?? event.type)}</strong><span
												class="text-xs text-muted-foreground">{event.year}</span
											>
										</div>
										<p class="mt-1 text-sm text-muted-foreground">
											{String(
												event.note ??
													event.reason ??
													event.rule ??
													event.change_id ??
													'Historická událost'
											)}
										</p>
									</div>{:else}<p class="text-sm text-muted-foreground">
										Pro tento jazyk zatím nejsou žádné události.
									</p>{/each}</CardContent
							></Card
						>
						<Card
							><CardHeader><CardTitle>Přidat autorskou událost</CardTitle></CardHeader><CardContent
								class="grid gap-3 md:grid-cols-[1fr_2fr_auto]"
								><Select bind:value={eventType}
									><option value="metadata">Změna metadat</option><option value="variety:assimilate"
										>Asimilace variety</option
									><option value="variety:split">Odštěpení variety</option><option
										value="institution">Institucionální změna</option
									><option value="migration">Migrace</option></Select
								><Input bind:value={eventNote} placeholder="Poznámka a historický důvod" /><Button
									variant="secondary"
									onclick={() => addAuthorEvent()}><Plus /> Přidat</Button
								></CardContent
							></Card
						>
					{:else if activeView === 'varieties'}
						<Card
							><CardHeader
								><CardTitle class="flex items-center gap-2"
									><GitBranch size={18} /> Variety a dialekty</CardTitle
								><CardDescription
									>Výsledek sám nemění strom jazyků; rozhodnutí je vždy autorovo.</CardDescription
								></CardHeader
							><CardContent class="grid gap-3 md:grid-cols-2"
								>{#each varieties as variety}<div class="rounded-lg border p-4">
										<strong>{variety.id}</strong>
										<p class="mt-1 text-xs text-muted-foreground">
											{variety.divergence !== undefined
												? `Divergence ${Math.round(Number(variety.divergence) * 100)} %`
												: (variety.kind ?? 'komunita')}
										</p>
										<div class="mt-3 flex flex-wrap gap-1">
											<Button
												size="xs"
												variant="outline"
												onclick={() => decideVariety(variety.id, 'assimilate')}>Asimilovat</Button
											><Button
												size="xs"
												variant="outline"
												onclick={() => decideVariety(variety.id, 'stabilize')}>Dialekt</Button
											><Button size="xs" onclick={() => decideVariety(variety.id, 'split')}
												>Nový jazyk</Button
											>
										</div>
									</div>{:else}<p class="text-sm text-muted-foreground">
										Přidej regionální či sociální komunity v nastavení jazyka; simulace pak sleduje
										jejich divergence.
									</p>{/each}</CardContent
							></Card
						>
					{:else if activeView === 'settings'}
						<Card
							><CardHeader
								><CardTitle>Sémantický režim</CardTitle><CardDescription
									>Určuje hustotu historických příležitostí; režim „ke schválení“ nespustí návrh bez
									potvrzení v časové ose.</CardDescription
								></CardHeader
							><CardContent class="grid gap-4 md:grid-cols-3"
								><Label
									>Tempo významových změn<Select
										value={languageData.semantic?.profile ?? 'balanced'}
										onchange={(event) => updateSemantic({ profile: event.currentTarget.value })}
										><option value="conservative">konzervativní</option><option value="balanced"
											>vyvážené</option
										><option value="dynamic">dynamické</option></Select
									></Label
								><Label
									>Uplatňování návrhů<Select
										value={languageData.semantic?.approval_mode ?? 'auto'}
										onchange={(event) =>
											updateSemantic({ approval_mode: event.currentTarget.value })}
										><option value="auto">automaticky</option><option value="review"
											>po schválení</option
										></Select
									></Label
								><Label
									>Ohnisko inovace<Select
										value={languageData.semantic?.innovation_group ?? ''}
										onchange={(event) =>
											updateSemantic({ innovation_group: event.currentTarget.value || undefined })}
										><option value="">nejsilnější komunita</option
										>{#each communities as community (community.id)}<option value={community.id}
												>{community.id}</option
											>{/each}</Select
									></Label
								></CardContent
							></Card
						>
						<Card
							><CardHeader
								><CardTitle>Názvy a identita</CardTitle><CardDescription
									>Endonymum je vlastní název mluvčích; exonymum je název užívaný zvenčí. Při
									odštěpení se upřednostní nepoužité kurátorované jméno.</CardDescription
								></CardHeader
							><CardContent class="grid gap-4 md:grid-cols-2"
								><Label>Jméno v projektu<Input bind:value={labelDraft} /></Label><Label
									>Endonymum<Input bind:value={endonymDraft} /></Label
								><Label>Exonymum<Input bind:value={exonymDraft} /></Label><Label
									>Autonomie názvu: {Math.round(nameAutonomyDraft * 100)} %<Input
										type="range"
										min="0"
										max="1"
										step="0.05"
										bind:value={nameAutonomyDraft}
									/></Label
								><Label class="md:col-span-2"
									>Kurátorovaná jména pro větvení (čárkou)<Input
										bind:value={namePoolDraft}
										placeholder="Velar, Saran, Nore"
									/></Label
								><Button class="md:col-span-2" onclick={saveName}><Save /> Uložit názvy</Button
								></CardContent
							></Card
						>
						<Card
							><CardHeader
								><CardTitle>Metadata v roce {selectedYear}</CardTitle><CardDescription
									>Změna se uloží do tohoto a následujících snímků časové osy.</CardDescription
								></CardHeader
							><CardContent class="grid gap-4 md:grid-cols-2"
								><Label>Název<Input bind:value={labelDraft} /></Label>
								<div class="flex items-end">
									<Button class="w-full" onclick={saveName}><Save /> Uložit název</Button>
								</div>
								<Label
									>Populace<Input
										type="number"
										value={languageData.population?.size ?? ''}
										oninput={(event) =>
											updateLanguageData({
												population: {
													...(languageData.population ?? {}),
													size: Number(event.currentTarget.value)
												}
											})}
									/></Label
								><Label
									>Počet center<Select
										value={String(languageData.population?.centers ?? 1)}
										onchange={(event) =>
											updateLanguageData({
												population: {
													...(languageData.population ?? {}),
													centers: Number(event.currentTarget.value)
												}
											})}
										><option value="1">1 — centralizovaná</option><option value="2">2</option
										><option value="3">3</option><option value="5">5+</option></Select
									></Label
								>
								<div class="space-y-3 rounded-md border p-3 md:col-span-2">
									<p class="text-sm font-medium">Morfologická historie</p>
									<label class="flex items-center gap-2 text-sm"
										><Checkbox
											checked={languageData.morphology?.enabled ?? false}
											onchange={(event: Event & { currentTarget: HTMLInputElement }) =>
												updateLanguageData({
													morphology: {
														...(languageData.morphology ?? {}),
														enabled: event.currentTarget.checked
													}
												})}
										/>Sledovat produktivní afixy, erozi a analogii</label
									><label class="flex items-center gap-2 text-sm"
										><Checkbox
											checked={languageData.morphology?.recipe_compounds ?? false}
											onchange={(event: Event & { currentTarget: HTMLInputElement }) =>
												updateLanguageData({
													morphology: {
														...(languageData.morphology ?? {}),
														recipe_compounds: event.currentTarget.checked
													}
												})}
										/>Doplňovat chybějící koncepty sémantickými recepty složenin</label
									>
									<p class="text-xs text-muted-foreground">
										Recept nikdy nenahradí existující kořen a použije se jen tehdy, když jazyk už
										obsahuje oba zdrojové lexémy.
									</p>
								</div>
								<div class="space-y-3 rounded-md border p-3 md:col-span-2">
									<p class="text-sm font-medium">Lexikální životní cyklus</p>
									<label class="flex items-center gap-2 text-sm"
										><Checkbox
											checked={languageData.lexical?.enabled ?? false}
											onchange={(event: Event & { currentTarget: HTMLInputElement }) =>
												updateLanguageData({
													lexical: {
														...(languageData.lexical ?? {}),
														enabled: event.currentTarget.checked
													}
												})}
										/>Nechat vznikat a soutěžit lexikální varianty</label
									><Label
										>Podíl náhrad, které mohou být novým motivovaným kořenem: {Math.round(
											Number(languageData.lexical?.innovation_rate ?? 0) * 100
										)} %<Input
											type="range"
											min="0"
											max="1"
											step="0.05"
											value={Number(languageData.lexical?.innovation_rate ?? 0)}
											oninput={(event) =>
												updateLanguageData({
													lexical: {
														...(languageData.lexical ?? {}),
														innovation_rate: Number(event.currentTarget.value)
													}
												})}
										/></Label
									>
									<p class="text-xs text-muted-foreground">
										Nové kořeny se tvoří z vlastní fonologie jazyka; audit označí motivaci jako
										expresivitu, dětskou řeč, obchodní slang nebo lokální substrát.
									</p>
								</div>
								<div class="space-y-3 rounded-md border p-3 md:col-span-2">
									<p class="text-sm font-medium">Společenské potřeby</p>
									<p class="text-xs text-muted-foreground">
										Tyto tlaky zvýhodní jen doložené sémantické změny v odpovídajících doménách.
									</p>
									{#each [['economy', 'Ekonomika'], ['technology', 'Technologie'], ['institutions', 'Instituce'], ['religion', 'Náboženství']] as [key, label]}<Label
											>{label}: {Math.round(
												Number(languageData.semantic?.pressures?.[key] ?? 0) * 100
											)} %<Input
												type="range"
												min="0"
												max="1"
												step="0.05"
												value={Number(languageData.semantic?.pressures?.[key] ?? 0)}
												oninput={(event) =>
													updatePressures({ [key]: Number(event.currentTarget.value) })}
											/></Label
										>{/each}<Button
										size="sm"
										variant="outline"
										onclick={() =>
											recordSocialChange(
												{
													institutions: Number(languageData.semantic?.pressures?.institutions ?? 0),
													mobility: Number(languageData.social?.mobility ?? 0.5)
												},
												'Změna společenských potřeb.'
											)}>Zapsat jako událost</Button
									>
								</div>
								<div class="space-y-3 rounded-md border p-3 md:col-span-2">
									<p class="text-sm font-medium">Registry a domény</p>
									<Label
										>Formalizace institucí: {Math.round(
											Number(languageData.semantic?.registers?.formalization ?? 0) * 100
										)} %<Input
											type="range"
											min="0"
											max="1"
											step="0.05"
											value={Number(languageData.semantic?.registers?.formalization ?? 0)}
											oninput={(event) =>
												updateRegisters({ formalization: Number(event.currentTarget.value) })}
										/></Label
									><Label
										>Šíření rituálního užití do běžné řeči: {Math.round(
											Number(languageData.semantic?.registers?.secularization ?? 0) * 100
										)} %<Input
											type="range"
											min="0"
											max="1"
											step="0.05"
											value={Number(languageData.semantic?.registers?.secularization ?? 0)}
											oninput={(event) =>
												updateRegisters({ secularization: Number(event.currentTarget.value) })}
										/></Label
									><Label
										>Tabuizované koncepty (oddělené čárkou)<Input
											value={(languageData.lexical?.taboo_concepts ?? []).join(', ')}
											oninput={(event) =>
												updateLanguageData({
													lexical: {
														...(languageData.lexical ?? {}),
														taboo_concepts: event.currentTarget.value
															.split(',')
															.map((value) => value.trim())
															.filter(Boolean)
													}
												})}
										/></Label
									>
								</div>
								<div class="space-y-3 rounded-md border p-3 md:col-span-2">
									<div class="flex items-center justify-between">
										<div>
											<p class="text-sm font-medium">Komunity a síť šíření</p>
											<p class="text-xs text-muted-foreground">
												Vazby a bilingvismus řídí šíření fonologických a varietních inovací;
												nepředstavují jednotlivé mluvčí.
											</p>
										</div>
										<Button size="sm" variant="outline" onclick={addCommunity}
											><Plus /> Přidat komunitu</Button
										>
									</div>
									{#each communities as community (community.id)}<div
											class="grid gap-2 rounded-md bg-muted/40 p-3 md:grid-cols-3"
										>
											<Label
												>ID<Input
													value={community.id}
													oninput={(event) =>
														patchCommunity(community.id, {
															id: event.currentTarget.value,
															variety_id: `variety:${event.currentTarget.value}`
														})}
												/></Label
											><Label
												>Podíl<Input
													type="number"
													min="0"
													max="1"
													step="0.05"
													value={community.share ?? 0.1}
													oninput={(event) =>
														patchCommunity(community.id, {
															share: Number(event.currentTarget.value)
														})}
												/></Label
											><Label
												>Generace<Select
													value={community.generation ?? 'mixed'}
													onchange={(event) =>
														patchCommunity(community.id, { generation: event.currentTarget.value })}
													><option value="young">mladá</option><option value="adult">dospělá</option
													><option value="mixed">smíšená</option><option value="elder"
														>starší</option
													></Select
												></Label
											><Label
												>Mobilita<Input
													type="range"
													min="0"
													max="1"
													step="0.05"
													value={community.mobility ?? 0.5}
													oninput={(event) =>
														patchCommunity(community.id, {
															mobility: Number(event.currentTarget.value)
														})}
												/></Label
											><Label
												>Městskost<Input
													type="range"
													min="0"
													max="1"
													step="0.05"
													value={community.urbanity ?? 0.5}
													oninput={(event) =>
														patchCommunity(community.id, {
															urbanity: Number(event.currentTarget.value)
														})}
												/></Label
											>
											<div class="flex items-end">
												<Button
													size="sm"
													variant="ghost"
													onclick={() => removeCommunity(community.id)}>Odebrat</Button
												>
											</div>
											{#each communities.filter((other) => other.id !== community.id) as other}<Label
													>Vazba → {other.id}<Input
														type="range"
														min="0"
														max="1"
														step="0.05"
														value={community.links?.[other.id] ?? 0}
														oninput={(event) =>
															patchCommunity(community.id, {
																links: {
																	...(community.links ?? {}),
																	[other.id]: Number(event.currentTarget.value)
																}
															})}
													/></Label
												><Label
													>Bilingvismus → {other.id}<Input
														type="range"
														min="0"
														max="1"
														step="0.05"
														value={community.bilingualism?.[other.id] ?? 0}
														oninput={(event) =>
															patchCommunity(community.id, {
																bilingualism: {
																	...(community.bilingualism ?? {}),
																	[other.id]: Number(event.currentTarget.value)
																}
															})}
													/></Label
												>{/each}
										</div>{:else}<p class="text-sm text-muted-foreground">
											Přidej alespoň dvě komunity, aby simulátor mohl modelovat síťové šíření a
											variety.
										</p>{/each}
								</div>
							</CardContent></Card
						>
					{:else if activeView === 'catalog'}
						<Card
							><CardHeader
								><CardTitle class="flex items-center gap-2"
									><Users size={18} /> Databáze jazyků</CardTitle
								><CardDescription>Všechny jazyky, které se v projektu objevily.</CardDescription
								></CardHeader
							><CardContent
								><Table
									><TableHeader
										><TableRow><TableHead>Jazyk</TableHead><TableHead>Od roku</TableHead></TableRow
										></TableHeader
									><TableBody
										>{#each catalog as item}<TableRow
												><TableCell
													><a
														class="text-primary hover:underline"
														href={`/project/${projectId}/languages/${item.id}?year=${selectedYear}`}
														>{item.label}</a
													></TableCell
												><TableCell>{item.year}</TableCell></TableRow
											>{/each}</TableBody
									></Table
								></CardContent
							></Card
						>
					{/if}
				</section>
			</div>
		{/if}
	</div>
</main>
