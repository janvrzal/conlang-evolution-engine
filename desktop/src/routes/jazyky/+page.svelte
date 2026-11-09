<!-- Jazyky: řeka jazyků (mluvčí doma v čase po rodinách), filtr a hledání; karta vybraného jazyka
     s původem, vlastním jménem, nářečími, mluvnicí a souhrnem zvukových změn a analogií. -->
<script lang="ts">
	import {
		Button,
		Card,
		Checkbox,
		Cluster,
		Area,
		Ipa,
		LanguageRiver,
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
		Text,
		TextInput,
		Tr,
		formatYear
	} from '$lib/ds';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import { geography } from '$lib/model/geography';
	import {
		biggestGroup,
		centurySummary,
		endonymHistory,
		grammarRows,
		presence,
		mergeVarieties,
		riverStreams,
		rootRetention,
		totals
	} from '$lib/model/jazyky';
	import { frameAt, lineageFamilies, lineageNames, lineagePalette, speakers, varietiesAt } from '$lib/model/languages';
	import { dialectNames, romanize } from '$lib/naming';
	import { app } from '$lib/state.svelte';

	type Tab = 'dialects' | 'grammar' | 'sounds' | 'analogy';
	let tab = $state<Tab>('sounds');
	let family = $state<string>('all');
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

	// karta jazyka
	const familyName = $derived(world && lineage ? (world.languages[families.get(lineage.id) ?? 0]?.name ?? '') : '');
	const endonyms = $derived(lineage ? endonymHistory(app.frames, lineage.id) : []);
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
	const unit = (rows: { counts: number[] }[], n: number) => totals(rows, n);
</script>

{#if !world || !result || !geo}
	<Screen><Stack gap={3}><Text variant="h1">{t('shell.nav.jazyky')}</Text><Text variant="why">{t('jazyky.empty')}</Text></Stack></Screen>
{:else}
	<Screen columns={['fill', 400]} label={t('jazyky.title', { year: formatYear(year) })}>
		<Area>
			<Cluster gap={3}>
				<Segmented label={t('jazyky.family')} bind:value={family} options={familyOptions} />
				<TextInput type="search" label={t('jazyky.search')} placeholder={t('jazyky.search')} bind:value={query} width="l" />
				{#if varieties}
					<Checkbox bind:checked={app.view.allLanguages} meta={t('atlas.small_count', { n: varieties.host.size + varieties.orphans.length })}>{t('shell.all_languages')}</Checkbox>
				{/if}
			</Cluster>
			<Stage tone="land" label={t('jazyky.river', { from: formatYear(app.frames[0]?.year ?? 0), to: formatYear(endYear) })}>
				<LanguageRiver
					years={river.years}
					streams={river.streams}
					{selected}
					cursor={year}
					label={t('jazyky.river', { from: formatYear(river.years[0] ?? 0), to: formatYear(endYear) })}
					onselect={pick}
				/>
			</Stage>
			<Text variant="why">
				{t('jazyky.why', { n: result.lineages.length })}
				{#if river.streams.length === 0}{t('jazyky.none')}{:else if river.streams.length < result.lineages.length}{t('jazyky.shown', { shown: river.streams.length, n: result.lineages.length })}{/if}
			</Text>
		</Area>

		{#if lineage}
			<Card label={t('jazyky.card', { name: nameOf(lineage.id) })}>
				<Stack gap={1}>
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t(lineage.parent ? 'jazyky.caps_daughter' : 'jazyky.caps_proto')}</Text>
						<Button variant="quiet" href="/protojazyky">*{familyName}</Button>
					</Cluster>
					<Text variant="h1"><Swatch color={palette.get(lineage.id) ?? 'var(--ink-3)'} /> {nameOf(lineage.id)}</Text>
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
						{#if sounds.length}
							<Table
								caption={t('jazyky.world_wide')}
								head={[{ label: t('jazyky.col.century'), num: true }, { label: t('jazyky.col.innovation'), num: true }, { label: t('jazyky.col.established'), num: true }, { label: t('jazyky.col.closed'), num: true }]}
							>
								{#each sounds as r (r.century)}
									<Tr><Td num>{formatYear(r.century)}</Td>{#each r.counts as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
								{/each}
								<Tr><Td num>{t('jazyky.total')}</Td>{#each unit(sounds, soundKinds.length) as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
							</Table>
						{:else}
							<Text variant="why">{t('jazyky.summary_none')}</Text>
						{/if}
					</Stack>
				{:else}
					<Stack gap={2}>
						<Text variant="why">{t('jazyky.analogy_intro')}</Text>
						{#if analogies.length}
							<Table
								caption={t('jazyky.world_wide')}
								head={[{ label: t('jazyky.col.century'), num: true }, { label: t('jazyky.col.analogy'), num: true }, { label: t('jazyky.col.gram'), num: true }]}
							>
								{#each analogies as r (r.century)}
									<Tr><Td num>{formatYear(r.century)}</Td>{#each r.counts as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
								{/each}
								<Tr><Td num>{t('jazyky.total')}</Td>{#each unit(analogies, analogyKinds.length) as n, i (i)}<Td num>{number(n)}</Td>{/each}</Tr>
							</Table>
						{:else}
							<Text variant="why">{t('jazyky.summary_none')}</Text>
						{/if}
					</Stack>
				{/if}
			</Card>
		{:else}
			<Card label={t('jazyky.no_pick')}><Text variant="why">{t('jazyky.no_pick')}</Text></Card>
		{/if}
	</Screen>
{/if}
