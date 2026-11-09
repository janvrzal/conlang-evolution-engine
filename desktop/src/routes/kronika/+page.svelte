<!-- Kronika: století s drobnými změnami (souhrn), pod nimi události autora, běhu a jazyků; vpravo vybraná událost. -->
<script lang="ts">
	import {
		Area,
		Button,
		Card,
		Checkbox,
		Cluster,
		Floating,
		Ledger,
		LedgerRow,
		List,
		ListItem,
		Screen,
		Stack,
		Table,
		Td,
		Text,
		TextInput,
		Tr,
		formatYear
	} from '$lib/ds';
	import { i18n, number, t } from '$lib/i18n.svelte';
	import { centuries, filterEvents, listEvents, mergeRows, type Cls, type KCentury, type KEvent, type KronikaContext, type KRow } from '$lib/model/kronika';
	import { geography } from '$lib/model/geography';
	import { lineageNames } from '$lib/model/languages';
	import { app } from '$lib/state.svelte';

	const MARK: Record<Cls, string> = { author: '■', lang: '◆', soc: '□' };

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const endYear = $derived(result?.year ?? app.run?.end_year ?? world?.end_year ?? 0);
	const year = $derived(app.view.year ?? (app.running ? Math.round(app.run?.year ?? 0) : endYear));
	const nowKey = $derived(Math.floor(year / 100) * 100);

	// jména: kraje z geografie, jazyky z výsledku (linie) a ze zadání (kódy), státy z výsledku a zadání
	const lineages = $derived(result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const stateNames = $derived.by(() => {
		const out = new Map<string, string>();
		for (const s of result?.states ?? []) out.set(s.id, s.name);
		for (const e of world?.events ?? []) if (e.kind === 'state' && typeof e.id === 'string' && typeof e.name === 'string') out.set(e.id, e.name);
		return out;
	});
	const regionIds = $derived(new Set(world?.regions.map((r) => r.id) ?? []));
	const ctx: KronikaContext = $derived({
		tr: t,
		names: {
			region: (id) => geo?.name(id) ?? id,
			lineage: (id) => lineages.get(id) ?? id,
			language: (code) => world?.languages.find((l) => l.id === code)?.name ?? code,
			state: (id) => stateNames.get(id) ?? id,
			known: (id) => regionIds.has(id)
		}
	});

	const authorCount = $derived(world?.events.length ?? 0);
	const all = $derived(world ? listEvents(world.events, result?.events ?? [], ctx) : []);
	let show = $state<Record<Cls, boolean>>({ author: true, soc: true, lang: true });
	let query = $state<string | number>('');
	const rows = $derived(mergeRows(filterEvents(all, { show, query: String(query) })));
	const blocks = $derived(
		centuries(world?.start_year ?? result?.start_year ?? 0, endYear, result?.event_summary, rows).filter((c) => c.rows.length || c.summary.length || c.key === nowKey)
	);

	// výběr: podle výběru Atlasu (app.view.event) nebo posledního kliknutí na řádek
	let picked = $state<string | null>(null);
	const selectedKey = $derived(app.view.event != null ? `a${app.view.event}` : picked);
	const selected = $derived(selectedKey ? (all.find((e) => e.key === selectedKey) ?? null) : null);
	const siblings = $derived(
		selected ? all.filter((e) => e.source === selected.source && e.year === selected.year && e.kind === selected.kind) : []
	);

	// století s rokem časové osy: když ho posune časová osa a není vidět, posune se k němu seznam
	let nowEl = $state<HTMLElement | undefined>();
	$effect(() => {
		void nowKey;
		nowEl?.scrollIntoView({ block: 'nearest' });
	});

	function choose(e: KEvent) {
		picked = e.key;
		app.view.year = e.year;
		app.view.event = e.source === 'author' ? e.index : null;
	}
	const isSelected = (row: KRow) => row.members.some((m) => m.key === selectedKey);
</script>

{#snippet century(c: KCentury)}
	<Stack gap={1}>
		<Text variant="big">{formatYear(c.from)}–{formatYear(c.to)}</Text>
		{#if c.summary.length}
			<Cluster gap={3}>
				{#each c.summary as s (s.id)}
					<Text variant="small">{t(`kronika.summary.${s.id}`)} <Text variant="strong">{number(s.value)}</Text></Text>
				{/each}
			</Cluster>
		{/if}
		{#if c.rows.length}
			<Table>
				{#each c.rows as row (row.key)}
					<Tr selected={isSelected(row)} onclick={() => choose(row.members[0])}>
						<Td num>{formatYear(row.year)}</Td>
						<Td><Text as="span" tone="muted">{MARK[row.cls]}</Text></Td>
						<Td>
							<Text as="span">{row.title}</Text>
							{#if row.text}<Text variant="why" as="span"> {row.text}</Text>{/if}
						</Td>
						<Td num>{row.count > 1 ? `${row.count}×` : ''}</Td>
					</Tr>
				{/each}
			</Table>
		{/if}
	</Stack>
{/snippet}

{#if !world || !geo}
	<Screen><Text variant="why">{t('check.running')}</Text></Screen>
{:else}
	<Screen columns={[240, 'fill', 320]} label={t('kronika.title')}>
		<Card label={t('kronika.filters')}>
			<Stack gap={1}>
				<Text variant="caps">{t('kronika.filters')}</Text>
				<Checkbox bind:checked={show.author} meta={number(authorCount)}>
					<Text as="span" tone="muted">{MARK.author}</Text>
					{t('kronika.filter.author')}
				</Checkbox>
				<Checkbox bind:checked={show.soc} meta={t('kronika.filter.soc_meta')}>
					<Text as="span" tone="muted">{MARK.soc}</Text>
					{t('kronika.filter.soc')}
				</Checkbox>
				<Checkbox bind:checked={show.lang} meta={t('kronika.filter.lang_meta')}>
					<Text as="span" tone="muted">{MARK.lang}</Text>
					{t('kronika.filter.lang')}
				</Checkbox>
			</Stack>
			<Text variant="why">{t('kronika.note')}</Text>
			<TextInput bind:value={query} type="search" label={t('kronika.search_label')} placeholder={t('kronika.search')} />
		</Card>

		<Area label={t('kronika.title')} scroll>
			{#if !result}
				<Text variant="why">{t('kronika.no_run')}</Text>
			{/if}
			{#each blocks as c (c.key)}
				{#if c.key === nowKey}
					<div bind:this={nowEl}><Floating>{@render century(c)}</Floating></div>
				{:else}
					{@render century(c)}
				{/if}
			{:else}
				<Text variant="why">{t('kronika.empty')}</Text>
			{/each}
		</Area>

		<Card label={t('kronika.card')}>
			{#if selected}
				<Stack gap={1}>
					<Text variant="caps">{formatYear(selected.year)} · {selected.source === 'author' ? t('kronika.src.author') : t('kronika.src.history')} · {selected.kindLabel}</Text>
					<Text variant="h1">{selected.title}</Text>
					{#if selected.text}<Text variant="why">{selected.text}</Text>{/if}
				</Stack>
				{#if selected.details.length}
					<Ledger>
						{#each selected.details as d (d.term)}
							<LedgerRow term={d.term}>{d.value}</LedgerRow>
						{/each}
					</Ledger>
				{/if}
				{#if siblings.length > 1}
					<Stack gap={1}>
						<Text variant="caps">{t('kronika.members', { n: siblings.length })}</Text>
						<List>
							{#each siblings as s (s.key)}
								<ListItem current={s.key === selectedKey} onclick={() => choose(s)}>{s.title}</ListItem>
							{/each}
						</List>
					</Stack>
				{/if}
				<Cluster>
					<Button href="/atlas">{t('kronika.open_atlas')}</Button>
					{#if selected.source === 'author'}<Button variant="quiet" href="/dejiny">{t('kronika.open_dejiny')}</Button>{/if}
				</Cluster>
			{:else}
				<Text variant="why">{t('kronika.hint')}</Text>
			{/if}
		</Card>
	</Screen>
{/if}
