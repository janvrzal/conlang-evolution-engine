<!-- Jazyky: řeka jazyků (mluvčí doma v čase po rodinách), filtr a hledání; karta vybraného jazyka
     s původem, vlastním jménem, nářečími, mluvnicí a souhrnem zvukových změn a analogií. -->
<script lang="ts">
	import {
		Area,
		Button,
		Card,
		Checkbox,
		Cluster,
		Disclosure,
		EmptyState,
		FamilyTree,
		Ipa,
		LanguageRiver,
		LanguageSigil,
		Ledger,
		LedgerRow,
		List,
		ListItem,
		Screen,
		Segmented,
		Stack,
		Stage,
		Swatch,
		Table,
		Tabs,
		Td,
		Term,
		Text,
		TextInput,
		Tr,
		formatYear,
		type TreeItem
	} from '$lib/ds';
	import { causeMessage, lineageObject, nameHistory, type NameHistory } from '$lib/model/jmena';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import { geography } from '$lib/model/geography';
	import {
		CELL_FUNCTION,
		analogyCounts,
		analogyRows,
		biggestGroup,
		centurySummary,
		endonymHistory,
		grammarRows,
		presence,
		mergeVarieties,
		parseFeatures,
		riverStreams,
		ruleText,
		soundRows,
		symText,
		type Sym,
		rootRetention,
		totals
	} from '$lib/model/jazyky';
	import { frameAt, lineageFamilies, lineageNames, lineagePalette, speakers, varietiesAt } from '$lib/model/languages';
	import { dialectNames, romanize } from '$lib/naming';
	import { app } from '$lib/state.svelte';

	type Tab = 'dialects' | 'grammar' | 'sounds' | 'analogy';
	let tab = $state<Tab>('sounds');
	let family = $state<string>('all');
	let view = $state<'river' | 'tree'>('river');
	let query = $state('');

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const endYear = $derived(result?.year ?? 0);
	const year = $derived(app.view.year ?? endYear);
	const atEnd = $derived(!!result && year >= result.year);
	const frame = $derived(frameAt(app.frames, year));
	const domainOf = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g.domain])));
	const spoken = $derived(frame ? speakers(frame.groups, domainOf) : new Map<string, number>());

	const names = $derived(result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const nameOf = (id: string | null) => (id ? (names.get(id) ?? id) : '—');
	const palette = $derived(world && result ? lineagePalette(world, result) : new Map<string, string>());
	const families = $derived(world && result ? lineageFamilies(world, result) : new Map<string, number>());

	// výběr: sdílený, jinak největší jazyk v roce kurzoru
	const largest = $derived([...spoken.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null);
	const selected = $derived(app.view.lineage && result?.lineages.some((l) => l.id === app.view.lineage) ? app.view.lineage : largest);
	const lineage = $derived(result?.lineages.find((l) => l.id === selected) ?? null);

	const familyFilter = $derived(family === 'all' ? null : Number(family));
	// malé jazyky jako variety (podle koncového stavu); „všechny jazyky“ ukáže stav enginu
	const varieties = $derived(result && world ? varietiesAt(world, result, result.groups) : null);
	const river = $derived.by(() => {
		if (!result || !world) return { years: [], streams: [] };
		const all = riverStreams(app.frames, domainOf, result.lineages, families, names, palette, { family: familyFilter, query }, selected);
		return varieties && !app.view.allLanguages ? mergeVarieties(all, varieties.host, selected) : all;
	});
	const familyOptions = $derived([
		{ value: 'all', label: t('jazyky.family_all') },
		...(world?.languages ?? []).map((l, i) => ({ value: String(i), label: l.name ?? l.id }))
	]);
	const pick = (id: string) => (app.view.lineage = id);
	// rodokmen: jazyky vybrané rodiny (nebo všech), tloušťka podle mluvčích v posledním snímku
	const tree = $derived.by((): TreeItem[] => {
		if (!result || view !== 'tree') return [];
		const last = app.frames[app.frames.length - 1];
		const now = last ? speakers(last.groups, domainOf) : new Map<string, number>();
		const said = last?.endonyms ?? {};
		return result.lineages
			.filter((l) => familyFilter == null || families.get(l.id) === familyFilter)
			.map((l) => ({ id: l.id, parent: l.parent, start: l.start_year, end: l.end_year, speakers: now.get(l.id) ?? 0, label: nameOf(l.id), color: palette.get(l.id) ?? 'var(--ink-3)', ipa: said[l.id] ?? l.endonym ?? undefined }));
	});

	// karta jazyka
	const familyName = $derived(world && lineage ? (world.languages[families.get(lineage.id) ?? 0]?.name ?? '') : '');
	const endonyms = $derived(lineage ? endonymHistory(app.frames, lineage.id) : []);
	const history = $derived(lineage ? nameHistory(result?.names, lineageObject(lineage.id)) : null);
	// historie jména z modulu jmen (export `names`)
	const motivation = (key: string) => {
		const label = t(`name.mot.${key}` as MessageKey);
		return label === `name.mot.${key}` ? key : label;
	};
	const causeText = (cause: string) => {
		const m = causeMessage(cause);
		return 'text' in m ? m.text : t(m.key as MessageKey, m.params);
	};
	const exonymSpeaker = (id: string) => nameOf(id);
	const here = $derived(frame && lineage ? presence(frame, lineage.id, domainOf) : null);
	const alive = $derived(!!lineage && (spoken.get(lineage.id) ?? 0) > 0);
	const retention = $derived(result && lineage ? rootRetention(result, lineage) : null);
	const originText = $derived(
		lineage
			? (lineage.parent
					? t('jazyky.origin_split', { year: formatYear(lineage.start_year), parent: nameOf(lineage.parent) })
					: t('jazyky.origin_root', { year: formatYear(lineage.start_year) })) +
					(lineage.origin_region && geo ? t('jazyky.origin_region', { region: geo.name(lineage.origin_region) }) : '')
			: ''
	);
	const nowText = $derived.by(() => {
		if (!lineage || !here) return '';
		if (alive) return t('jazyky.now', { people: number(here.speakers), villages: here.villages }) + (lineage.id === largest ? t('jazyky.largest') : '');
		if (lineage.end_year != null && lineage.end_year <= year) return t('jazyky.extinct', { year: formatYear(lineage.end_year) });
		return t('jazyky.unborn', { year: formatYear(lineage.start_year) });
	});

	// nářečí ve snímku roku
	const dialects = $derived.by(() => {
		if (!frame || !lineage || !geo) return { big: [] as { name: string; n: number }[], single: 0 };
		const facts = frame.dialect_facts.filter((d) => d.lineage === lineage.id);
		const labels = dialectNames(facts, geo.name, i18n.locale);
		const big = facts.map((d, i) => ({ name: labels[i], n: d.groups.length })).filter((d) => d.n > 1).sort((a, b) => b.n - a.n);
		return { big, single: facts.length - big.length };
	});

	// mluvnice největší skupiny (jen koncový export)
	const mainGroup = $derived(result && lineage ? biggestGroup(result, lineage.id) : null);
	const grammar = $derived(result && mainGroup ? grammarRows(result.grammar[mainGroup]) : []);
	const how = (kind: string, order: string | null) => {
		const base = t(`jazyky.kind.${kind}` as MessageKey);
		return order ? `${base}, ${order}` : base;
	};

	// souhrny po stoletích (celý svět)
	const soundKinds = ['innovation', 'established', 'process_closed'];
	const analogyKinds = ['analogy', 'grammaticalized'];
	const sounds = $derived(centurySummary(result?.event_summary, soundKinds));
	const analogies = $derived(centurySummary(result?.event_summary, analogyKinds));

	// zvuky a analogie vybraného jazyka (change_history), nejrozšířenější první
	const PAGE = 30;
	let soundShown = $state(PAGE);
	let analogyShown = $state(PAGE);
	$effect(() => {
		void selected;
		soundShown = PAGE;
		analogyShown = PAGE;
	});
	const soundList = $derived(soundRows(result, selected));
	const analogyList = $derived(analogyRows(result, selected));
	const analogyTotals = $derived(analogyCounts(analogyList));
	const featureExplain = (spec: string) =>
		parseFeatures(spec)
			.map((f) => (f.known ? t(`jazyky.feat.${f.name}.${f.plus ? 'plus' : 'minus'}` as MessageKey) : (f.plus ? '+' : '−') + f.name))
			.join(', ');
	const classText = (s: Sym) => (s.kind === 'class' ? t(`jazyky.cls.${s.id}` as MessageKey) : t('jazyky.cls.edge'));
	const cellText = (cell: string | null) => (cell ? (CELL_FUNCTION[cell] ? t(`jazyky.fn.${CELL_FUNCTION[cell]}` as MessageKey) : cell) : '—');
	const unit = (rows: { counts: number[] }[], n: number) => totals(rows, n);
</script>

{#snippet nameHistoryBlock(h: NameHistory | null)}
	{#if h?.current}
		{@const cur = h.current}
		<Disclosure>
			{#snippet summary()}{t('name.history')} · {t('name.current', { name: cur.name, year: formatYear(cur.founded) })}{/snippet}
			<Stack gap={2}>
				<Ledger termWidth={110}>
					<LedgerRow term={t('name.motivation')}
						>{motivation(cur.motivation)}{#if cur.meaning}{' '}<Text variant="why" as="span">{t('jmena.meaning', { meaning: cur.meaning })}</Text>{/if}</LedgerRow
					>
					{#each cur.timeline as step, i (i)}
						<LedgerRow term={formatYear(step.year)}><Ipa text={step.ipa} />{' '}{step.name}{' '}<Text variant="why" as="span">{causeText(step.cause)}</Text></LedgerRow>
					{/each}
				</Ledger>
				{#if h.earlier.length}
					<Text variant="caps">{t('name.earlier')}</Text>
					<Ledger termWidth={110}>
						{#each h.earlier as r (r.id)}
							<LedgerRow term={t('name.ended', { from: formatYear(r.founded), to: r.ended != null ? formatYear(r.ended) : '…' })}
								>{r.name}{' '}<Ipa text={r.ipa} />{' '}<Text variant="why" as="span">{motivation(r.motivation)}</Text></LedgerRow
							>
						{/each}
					</Ledger>
				{/if}
				{#if h.exonyms.length}
					<Text variant="caps">{t('name.exonyms')}</Text>
					<Ledger termWidth={110}>
						{#each h.exonyms as e (e.lineage)}
							<LedgerRow term={exonymSpeaker(e.lineage)}>{e.record.name}{' '}<Ipa text={e.record.ipa} /></LedgerRow>
						{/each}
					</Ledger>
				{/if}
			</Stack>
		</Disclosure>
	{/if}
{/snippet}

{#if !world || !result || !geo}
	<Screen><EmptyState title={t('shell.nav.jazyky')} text={t('jazyky.empty')}
			>{#snippet actions()}<Button
					variant="primary"
					disabled={!app.world || app.running || app.errors.length > 0 || app.engineState.phase !== 'ready'}
					onclick={() => app.start()}>{t('shell.run', { from: formatYear(app.world?.start_year ?? 0), to: formatYear(app.world?.end_year ?? 0) })}</Button
				>{/snippet}</EmptyState
		></Screen>
{:else}
	<Screen columns={['fill', 400]} label={t('jazyky.title', { year: formatYear(year) })}>
		<Area>
			<Cluster gap={3}>
				<Segmented
					label={t('jazyky.view')}
					bind:value={view}
					options={[
						{ value: 'river', label: t('jazyky.view.river') },
						{ value: 'tree', label: t('jazyky.view.tree') }
					]}
				/>
				<Segmented label={t('jazyky.family')} bind:value={family} options={familyOptions} />
				<TextInput type="search" label={t('jazyky.search')} placeholder={t('jazyky.search')} bind:value={query} width="l" />
				{#if varieties}
					<Checkbox bind:checked={app.view.allLanguages} meta={t('atlas.small_count', { n: varieties.host.size + varieties.orphans.length })}>{t('shell.all_languages')}</Checkbox>
				{/if}
			</Cluster>
			<Stage tone="land" label={t('jazyky.river', { from: formatYear(app.frames[0]?.year ?? 0), to: formatYear(endYear) })}>
				{#if view === 'tree'}
					<FamilyTree items={tree} now={endYear} cursor={year} {selected} label={t('jazyky.tree', { from: formatYear(app.frames[0]?.year ?? 0), to: formatYear(endYear) })} onselect={pick} />
				{:else}
					<LanguageRiver
						years={river.years}
						streams={river.streams}
						{selected}
						cursor={year}
						label={t('jazyky.river', { from: formatYear(river.years[0] ?? 0), to: formatYear(endYear) })}
						onselect={pick}
					/>
				{/if}
			</Stage>
			<Text variant="why">
				{#if view === 'tree'}{t('jazyky.tree_why', { n: tree.length })}{:else}{t('jazyky.why', { n: result.lineages.length })}
				{#if river.streams.length === 0}{t('jazyky.none')}{:else if river.streams.length < result.lineages.length}{t('jazyky.shown', { shown: river.streams.length, n: result.lineages.length })}{/if}{/if}
			</Text>
		</Area>

		{#if lineage}
			<Card label={t('jazyky.card', { name: nameOf(lineage.id) })}>
				<Stack gap={1}>
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t(lineage.parent ? 'jazyky.caps_daughter' : 'jazyky.caps_proto')}</Text>
						<Button variant="quiet" href="/protojazyky">*{familyName}</Button>
					</Cluster>
					<Text variant="h1"
						>{#if endonyms.length}<LanguageSigil ipa={endonyms[endonyms.length - 1].ipa} color={palette.get(lineage.id) ?? 'var(--ink-3)'} size={34} />{:else}<Swatch
								color={palette.get(lineage.id) ?? 'var(--ink-3)'}
							/>{/if}
						{nameOf(lineage.id)}</Text
					>
					{#if endonyms.length}
						{@const last = endonyms[endonyms.length - 1]}
						<Text>{t('jazyky.says')} <i>{romanize(last.ipa)}</i> <Ipa text={last.ipa} slashes /> <Text variant="why" as="span">{t('jazyky.since', { year: formatYear(last.year) })}</Text></Text>
					{/if}
				</Stack>
				<Ledger termWidth={110}>
					<LedgerRow term={t('jazyky.row.origin')}>{originText}</LedgerRow>
					<LedgerRow term={t('jazyky.row.now', { year: formatYear(year) })}>{nowText}</LedgerRow>
					<LedgerRow term={t('jazyky.row.endonym')}>
						{#each endonyms as e, i (e.year)}{#if i > 0}{' → '}{/if}<Text variant="why" as="span" num>{formatYear(e.year)}</Text> <Ipa text={e.ipa} />{:else}—{/each}
					</LedgerRow>
					<LedgerRow term={t('jazyky.row.retention')}>
						{#if retention != null}<Text as="span" num>{number(Math.round(retention * 100) / 100)}</Text> <Text variant="why" as="span">{t('jazyky.retention_note')}</Text>{:else}<Text variant="why" as="span">{t('jazyky.retention_none')}</Text>{/if}
					</LedgerRow>
				</Ledger>
				{@render nameHistoryBlock(history)}

				<Tabs
					label={t('jazyky.tabs')}
					bind:value={tab}
					tabs={(['dialects', 'grammar', 'sounds', 'analogy'] as const).map((id) => ({ id, label: t(`jazyky.tab.${id}` as MessageKey) }))}
				/>

				{#if tab === 'dialects'}
					<Stack gap={2}>
						<Text variant="why">{t('jazyky.dialects_intro', { year: formatYear(year) })}</Text>
						{#if dialects.big.length || dialects.single}
							<List label={t('jazyky.tab.dialects')}>
								{#each dialects.big as d, i (i)}<ListItem meta={t('jazyky.dialect_villages', { n: d.n })}>{d.name}</ListItem>{/each}
								{#if dialects.single}<ListItem meta={t('jazyky.dialect_single_meta')}><Text variant="why" as="span">{t('jazyky.dialect_single', { n: dialects.single })}</Text></ListItem>{/if}
							</List>
						{:else}
							<Text variant="why">{t('jazyky.dialects_none')}</Text>
						{/if}
					</Stack>
				{:else if tab === 'grammar'}
					<Stack gap={2}>
						{#if !atEnd}
							<Text variant="why">{t('jazyky.grammar_end_only')}</Text>
						{:else if grammar.length}
							<Text variant="why">{t('jazyky.grammar_intro', { group: mainGroup ?? '' })}</Text>
							<Table head={[{ label: t('jazyky.col.function') }, { label: t('jazyky.col.how') }, { label: t('jazyky.col.from') }]}>
								{#each grammar as r (r.fn)}
									<Tr>
										<Td>{t(`jazyky.fn.${r.fn}` as MessageKey)}</Td>
										<Td>{how(r.kind, r.order)}{#if r.exponent} <Ipa text={'-' + r.exponent} />{/if}</Td>
										<Td>{r.source ? conceptLabel(r.source, i18n.locale) : '—'}</Td>
									</Tr>
								{/each}
							</Table>
							<Text variant="why">{t('jazyky.grammar_no_proto')}</Text>
						{:else}
							<Text variant="why">{t('jazyky.grammar_none')}</Text>
						{/if}
					</Stack>
				{:else if tab === 'sounds'}
					<Stack gap={2}>
						<Text variant="why">{t('jazyky.sounds_intro')}</Text>
						{#if soundList.length}
							<Text variant="why">{t('jazyky.sounds_total', { n: number(soundList.length) })}</Text>
							<Table head={[{ label: t('jazyky.col.from_year'), num: true }, { label: t('jazyky.col.change') }, { label: t('jazyky.col.villages'), num: true }]}>
								{#each soundList.slice(0, soundShown) as r (r.key)}
									<Tr>
										<Td num>{formatYear(r.year)}</Td>
										<Td>
											<Text variant="strong">{t(`jazyky.sfam.${r.family}` as MessageKey)}</Text><br />
											{@render sym(r.target)} {t(`jazyky.sop.${r.operation}` as MessageKey)}{#if r.features}{' '}<Term explain={featureExplain(r.features)}>[{r.features.replaceAll('-', '−')}]</Term>{/if}
											{#each [['left', r.left], ['right', r.right]] as const as [side, s] (side)}{#if s}
													{' · '}{t(`jazyky.ctx.${side}` as MessageKey)}{' '}{@render sym(s)}{/if}{/each}{#if r.stress}
{' · '}{t(`jazyky.ctx.${r.stress}` as MessageKey)}{/if}{#if r.medial}
{' · '}{t('jazyky.ctx.medial')}{/if}<br />
											<Ipa text={ruleText(r)} tone="muted" />{#if r.hiddenResult}
												<Term explain={t('jazyky.sound_hidden')}>…</Term>{/if}<br />
											<Text variant="why" as="span">{t('jazyky.sound_meta', { closed: r.closed, n: r.villages, relics: r.relics })}</Text>
										</Td>
										<Td num>{number(r.villages)}</Td>
									</Tr>
								{/each}
							</Table>
							{#if soundList.length > soundShown}
								<Button variant="quiet" onclick={() => (soundShown += PAGE)}>{t('jazyky.more_n', { n: Math.min(PAGE, soundList.length - soundShown) })}</Button>
							{/if}
						{:else}
							<Text variant="why">{t('jazyky.sounds_none')}</Text>
						{/if}
						{@render worldTable(sounds, soundKinds, ['innovation', 'established', 'closed'])}
					</Stack>
				{:else}
					<Stack gap={2}>
						<Text variant="why">{t('jazyky.analogy_intro')}</Text>
						{#if analogyList.length}
							<Text variant="why">
								{t('jazyky.analogy_total', { n: number(analogyList.length) })}:
								{#each analogyTotals as a, i (a.operation)}{i ? ', ' : ''}{t('jazyky.analogy_count', { n: number(a.count) })} {t(`jazyky.aop.${a.operation}` as MessageKey)}{/each}.
							</Text>
							<Table head={[{ label: t('jazyky.col.from_year'), num: true }, { label: t('jazyky.col.operation') }, { label: t('jazyky.col.concept') }, { label: t('jazyky.col.cell') }, { label: t('jazyky.col.villages'), num: true }]}>
								{#each analogyList.slice(0, analogyShown) as r (r.key)}
									<Tr>
										<Td num>{formatYear(r.year)}</Td>
										<Td>{t(`jazyky.aop.${r.operation}` as MessageKey)}</Td>
										<Td>{r.concept ? conceptLabel(r.concept, i18n.locale) : '—'}</Td>
										<Td>{cellText(r.cell)}</Td>
										<Td num>{number(r.villages)}</Td>
									</Tr>
								{/each}
							</Table>
							{#if analogyList.length > analogyShown}
								<Button variant="quiet" onclick={() => (analogyShown += PAGE)}>{t('jazyky.more_n', { n: Math.min(PAGE, analogyList.length - analogyShown) })}</Button>
							{/if}
						{:else}
							<Text variant="why">{t('jazyky.analogy_none')}</Text>
						{/if}
						{@render worldTable(analogies, analogyKinds, ['analogy', 'gram'])}
					</Stack>
				{/if}
			</Card>
		{:else}
			<Card label={t('jazyky.no_pick')}><Text variant="why">{t('jazyky.no_pick')}</Text></Card>
		{/if}
	</Screen>
{/if}

{#snippet sym(s: Sym | null)}
	{#if s?.kind === 'ipa'}<Ipa text={symText(s)} />{:else if s?.kind === 'features'}<Term explain={featureExplain(s.spec)}>[{s.spec.replaceAll('-', '−')}]</Term>{:else if s}{classText(s)}{/if}
{/snippet}

<!-- souhrn po stoletích za celý svět, jako doplněk pod jazykem -->
{#snippet worldTable(rows: { century: number; counts: number[] }[], kinds: string[], cols: string[])}
	{#if rows.length}
		<Disclosure>
			{#snippet summary()}{t('jazyky.world_summary')}{/snippet}
			<Table
				caption={t('jazyky.world_wide')}
				head={[{ label: t('jazyky.col.century'), num: true }, ...cols.map((c) => ({ label: t(`jazyky.col.${c}` as MessageKey), num: true }))]}
			>
				{#each rows as r (r.century)}
					<Tr><Td num>{formatYear(r.century)}</Td>{#each r.counts as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
				{/each}
				<Tr><Td num>{t('jazyky.total')}</Td>{#each unit(rows, kinds.length) as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
			</Table>
		</Disclosure>
	{/if}
{/snippet}
