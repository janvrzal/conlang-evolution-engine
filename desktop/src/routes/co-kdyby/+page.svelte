<!-- Co kdyby: dvě větve dějin vedle sebe (A hlavní běh, B větev), obě mapy přiblížené na vsi, kde se jazyk doma liší.
     Bez větve vysvětlí, k čemu slouží, a nabídne vytvořit ji vynecháním vybrané události. -->
<script lang="ts">
	import {
		Area,
		Banner,
		Button,
		Card,
		Cluster,
		Floating,
		Ledger,
		LedgerRow,
		Legend,
		MiniBars,
		Screen,
		Select,
		Stack,
		Stage,
		Table,
		Td,
		Text,
		Tr,
		WorldMap,
		familyColor,
		formatYear,
		type Hatch,
		type EdgeStyle,
		type LegendItem,
		type MapLabel,
		type MapVillage
	} from '$lib/ds';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import {
		compareWords,
		differingFamilies,
		differingVillages,
		domainsOf,
		familySpeakers,
		focusRegions,
		matchLineages,
		regionGroup,
		sideHome,
		withoutEvent,
		worldDifference
	} from '$lib/model/cokdyby';
	import { conceptLabel } from '$lib/model/concepts';
	import { geography } from '$lib/model/geography';
	import { frameAt, lineageFamilies, lineageNames, lineagePalette } from '$lib/model/languages';
	import { app } from '$lib/state.svelte';

	let zoomed = $state(true);
	let pickEvent = $state(-1);

	const world = $derived(app.world);
	const result = $derived(app.result);
	const branch = $derived(app.branch);
	const resultB = $derived(branch?.result ?? null);
	const worldB = $derived(branch?.world ?? null);
	const geo = $derived(world ? geography(world, result) : null);
	const ready = $derived(!!(world && result && geo && branch && resultB && worldB));

	const year = $derived(Math.min(app.view.year ?? result?.year ?? 0, result?.year ?? 0));
	const frameA = $derived(frameAt(app.frames, year));
	const frameB = $derived(branch ? frameAt(branch.frames, year) : null);
	const homeA = $derived(frameA && result ? sideHome(frameA, result) : new Map());
	const homeB = $derived(frameB && resultB ? sideHome(frameB, resultB) : new Map());
	const families = $derived(world && result && worldB && resultB ? { a: lineageFamilies(world, result), b: lineageFamilies(worldB, resultB) } : null);
	const match = $derived(matchLineages(homeA, homeB, families ?? undefined));
	const diff = $derived(differingVillages(homeA, homeB, match));

	// rámování: rozdíl na konci běhu a kraje kolem něj
	const endA = $derived(result ? frameAt(app.frames, result.year) : null);
	const endB = $derived(resultB && branch ? frameAt(branch.frames, resultB.year) : null);
	const diffEnd = $derived.by(() => {
		if (!endA || !endB || !result || !resultB) return new Set<string>();
		const a = sideHome(endA, result), b = sideHome(endB, resultB);
		return differingVillages(a, b, matchLineages(a, b, families ?? undefined));
	});
	const regionById = $derived(new Map((geo?.regions ?? []).map((r) => [r.id, r])));
	const focusSet = $derived(focusRegions(diffEnd, geo?.regionOf ?? new Map(), (r) => regionById.get(r)?.neighbours ?? []));
	const focus = $derived(zoomed && focusSet.core.size ? (geo?.villages ?? []).filter((v) => focusSet.all.has(v.region)).map((v) => v.id) : null);
	const diffRegionCount = $derived(new Set([...diff].map((v) => geo?.regionOf.get(v))).size);

	// vybraný kraj: z výběru, jinak kraj s největším rozdílem
	const diffByRegion = $derived.by(() => {
		const count = new Map<string, number>();
		for (const v of diffEnd) {
			const r = geo?.regionOf.get(v);
			if (r) count.set(r, (count.get(r) ?? 0) + 1);
		}
		return [...count.entries()].sort((a, b) => b[1] - a[1]).map(([r]) => r);
	});
	const selected = $derived(app.view.region ?? diffByRegion[0] ?? null);

	// jména a barvy; jazyk B spárovaný s A má barvu a jméno z A
	const namesA = $derived(world && result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const namesB = $derived(resultB && geo && branch ? lineageNames(resultB, geo.name, i18n.locale, branch.frames) : new Map<string, string>());
	const paletteA = $derived(world && result ? lineagePalette(world, result) : new Map<string, string>());
	const paletteB = $derived(worldB && resultB ? lineagePalette(worldB, resultB) : new Map<string, string>());
	const colorA = (lin: string | undefined) => (lin ? (paletteA.get(lin) ?? null) : null);
	const colorB = (lin: string | undefined) => {
		if (!lin) return null;
		const a = match.get(lin);
		return a ? colorA(a) : (paletteB.get(lin) ?? null);
	};

	const stateMap = (frame: typeof frameA) => new Map((frame?.states ?? []).flatMap((s) => s.regions.map((r) => [r, s.id] as const)));
	const statesA = $derived(stateMap(frameA));
	const statesB = $derived(stateMap(frameB));

	const fillA = $derived((v: MapVillage) => colorA(homeA.get(v.id)?.lineage));
	const fillB = $derived((v: MapVillage) => colorB(homeB.get(v.id)?.lineage));
	const hatch = $derived((v: MapVillage): Hatch | null => (diff.has(v.id) ? { angle: -Math.PI / 4, color: 'red', gap: 7, width: 0.8 } : null));
	const edgeOf = (states: Map<string, string>) => (a: MapVillage, b: MapVillage): EdgeStyle | null => {
		if (diff.has(a.id) !== diff.has(b.id)) return { color: 'red', width: 2.6 };
		if (a.region !== b.region && states.get(a.region) !== states.get(b.region)) return { color: 'ink', width: 1.1, dash: 'state' };
		return null;
	};
	const edgeA = $derived(edgeOf(statesA));
	const edgeB = $derived(edgeOf(statesB));
	const labels = $derived.by((): MapLabel[] => {
		if (!geo) return [];
		const out: MapLabel[] = [];
		const ids = focus ? focusSet.all : new Set([...focusSet.core, ...(selected ? [selected] : [])]);
		for (const id of ids) out.push({ text: geo.name(id), region: id, kind: focusSet.core.has(id) || id === selected ? 'strong' : 'region' });
		return out;
	});

	const summary = $derived(t('cokdyby.summary', { n: diff.size, regions: diffRegionCount }));
	const legend: LegendItem[] = $derived([
		...(world?.languages ?? []).map((l, i) => ({ label: l.name ?? l.id, color: familyColor(i) })),
		{ label: t('cokdyby.legend_diff'), kind: 'hatch' as const, color: 'var(--red)' },
		{ label: t('cokdyby.legend_state'), kind: 'dashed' as const }
	]);

	// události, kterými se větve liší
	const stateName = (id: string) => result?.states.find((s) => s.id === id)?.name ?? id;
	function eventLabel(e: { kind: string; year: number; [k: string]: unknown }, withYear = true) {
		const key = `kind.${e.kind}`;
		const kind = t(key as MessageKey) === key ? e.kind : t(key as MessageKey);
		const who = typeof e.name === 'string' ? e.name : typeof e.state === 'string' ? stateName(e.state) : '';
		return [kind, who, withYear ? formatYear(e.year) : ''].filter(Boolean).join(' ');
	}
	const difference = $derived(world && worldB ? worldDifference(world, worldB) : null);
	const listEvents = (list: { kind: string; year: number }[]) => list.map((e) => eventLabel(e)).join(', ');
	const whyA = $derived(difference?.onlyA.length ? t('cokdyby.a_with', { events: listEvents(difference.onlyA) }) : t('cokdyby.a_all'));
	const whyB = $derived.by(() => {
		if (!difference) return '';
		const parts = [];
		if (difference.onlyA.length) parts.push(t('cokdyby.b_without', { events: listEvents(difference.onlyA) }));
		if (difference.onlyB.length) parts.push(t('cokdyby.b_with', { events: listEvents(difference.onlyB) }));
		return parts.join('; ') || t('cokdyby.b_same');
	});
	const cardWhy = $derived.by(() => {
		if (!difference || difference.year == null) return t('cokdyby.card_why_same');
		const first = difference.onlyA[0] ?? difference.onlyB[0];
		return first ? t('cokdyby.card_why', { year: formatYear(difference.year), events: eventLabel(first, false) }) : t('cokdyby.card_why_year', { year: formatYear(difference.year) });
	});

	// sčítání kraje doma v A a B
	const familyName = (code: string) => world?.languages.find((l) => l.id === code)?.name ?? code;
	function homeShares(census: Record<string, number> | undefined) {
		const sorted = Object.entries(census ?? {}).sort((a, b) => b[1] - a[1]);
		const shown = sorted.filter(([, v], i) => i === 0 || v >= 0.15).slice(0, 2);
		return shown.map(([code, v]) => t('cokdyby.share', { pct: Math.round(v * 100), family: familyName(code) })).join(', ');
	}
	const censusRows = $derived.by(() => {
		if (!frameA || !frameB || !geo) return [];
		const order = [...new Set([...(selected && diffRegionOf(selected) ? [selected] : []), ...diffByRegion])].slice(0, 2);
		return order.map((r) => {
			const a = homeShares(frameA.census[r]?.home), b = homeShares(frameB.census[r]?.home);
			return { region: geo.name(r), a, b, differs: a !== b };
		});
	});
	const diffRegionOf = (r: string) => diffByRegion.includes(r);

	// mluvčí rodin doma a počet jazyků
	const speakerRow = $derived.by(() => {
		if (!frameA || !frameB || !result || !resultB || !families) return null;
		const sa = familySpeakers(frameA, domainsOf(result), families.a), sb = familySpeakers(frameB, domainsOf(resultB), families.b);
		let best: { family: number; a: number; b: number } | null = null;
		for (const f of new Set([...sa.keys(), ...sb.keys()])) {
			const a = sa.get(f) ?? 0, b = sb.get(f) ?? 0;
			if (a !== b && (!best || Math.abs(a - b) > Math.abs(best.a - best.b))) best = { family: f, a, b };
		}
		return best;
	});
	const langsA = $derived(frameA ? Object.keys(frameA.languages).length : 0);
	const langsB = $derived(frameB ? Object.keys(frameB.languages).length : 0);

	// vsi s jinou rodinou doma ve snímcích od větvení
	const curve = $derived.by(() => {
		if (!families || !result || !resultB || !branch) return null;
		const from = difference?.year ?? 0;
		const years = app.frames.map((f) => f.year).filter((y) => y <= year);
		const base = Math.max(...years.filter((y) => y <= from), years[0] ?? 0);
		const list = years.filter((y) => y >= base);
		if (!list.length) return null;
		const values = list.map((y) => {
			const fa = frameAt(app.frames, y), fb = frameAt(branch.frames, y);
			return fa && fb ? differingFamilies(sideHome(fa, result), sideHome(fb, resultB), families.a, families.b) : 0;
		});
		return { labels: list.map((y) => formatYear(y)), values };
	});

	// slova vybraného kraje
	const CONCEPTS = ['water', 'stone', 'mother', 'king', 'fire', 'person', 'dog', 'eye'];
	const atEnd = $derived(!!result && year >= result.year);
	const words = $derived.by(() => {
		if (!selected || !geo || !result || !resultB || !endA || !endB || !atEnd) return null;
		const ga = regionGroup(endA, result, geo.villages, selected), gb = regionGroup(endB, resultB, geo.villages, selected);
		return compareWords(result, ga, resultB, gb, CONCEPTS);
	});

	// nová větev
	const events = $derived((world?.events ?? []).map((e, i) => ({ value: i, label: eventLabel(e), year: e.year })).sort((a, b) => a.year - b.year));
	const canStart = $derived(app.engineState.phase === 'ready' && !!result);
	const reason = $derived(!result ? t('cokdyby.need_run') : app.engineState.phase !== 'ready' ? t('cokdyby.need_engine') : pickEvent < 0 ? t('cokdyby.need_event') : '');
	function start() {
		if (!world || pickEvent < 0 || !canStart) return;
		const event = world.events[pickEvent];
		void app.startBranch(t('cokdyby.branch_label', { event: eventLabel(event) }), withoutEvent(world, pickEvent));
	}
	const pick = (r: string) => (app.view.region = r);
</script>

{#if !world}
	<Screen><Text variant="why">{t('cokdyby.none_explain')}</Text></Screen>
{:else if ready && geo && result && resultB}
	<Screen columns={['fill', 'fill', 380]} rows={['auto', 'fill', 'auto']} label={t('cokdyby.title', { year: formatYear(year) })}>
		<Area>
			<Text variant="h2">{t('cokdyby.head_a')} <Text variant="why" as="span">{whyA}</Text></Text>
		</Area>
		<Area>
			<Text variant="h2"><Text as="span" tone="red">B</Text> · {t('cokdyby.head_b')} <Text variant="why" as="span">{whyB}</Text></Text>
		</Area>
		<Card label={t('cokdyby.card')} rowSpan={3}>
			<Stack gap={1}>
				<Text variant="caps">{t('cokdyby.caps', { year: formatYear(year) })}</Text>
				<Text variant="h1">{t('cokdyby.card_title', { n: diff.size })}</Text>
				<Text variant="why">{cardWhy}</Text>
			</Stack>
			<Ledger termWidth={110}>
				{#each censusRows as row (row.region)}
					<LedgerRow term={t('cokdyby.home_of', { region: row.region })}>A: {row.a || '—'} · <Text as="span" tone={row.differs ? 'red' : undefined}>B: {row.b || '—'}</Text></LedgerRow>
				{/each}
				{#if speakerRow}
					<LedgerRow term={t('cokdyby.speakers_of', { family: familyName(world.languages[speakerRow.family]?.id ?? '') })}
						>A: <Text as="span" num>{number(speakerRow.a)}</Text> · <Text as="span" tone="red" num>B: {number(speakerRow.b)}</Text>
						<Text variant="why" as="span"
							>{t(speakerRow.b < speakerRow.a ? 'cokdyby.speakers_diff_less' : 'cokdyby.speakers_diff_more', { n: number(Math.abs(speakerRow.a - speakerRow.b)) })}</Text
						></LedgerRow
					>
				{/if}
				<LedgerRow term={t('cokdyby.languages')}
					>A: <Text as="span" num>{langsA}</Text> · <Text as="span" tone={langsA !== langsB ? 'red' : undefined} num>B: {langsB}</Text>
					{#if langsA !== langsB}<Text variant="why" as="span">{t(langsB < langsA ? 'cokdyby.languages_less' : 'cokdyby.languages_more', { n: Math.abs(langsA - langsB) })}</Text>{/if}</LedgerRow
				>
			</Ledger>
			{#if curve}
				<Stack gap={1}>
					<Text variant="caps">{t('cokdyby.curve')}</Text>
					<MiniBars values={curve.values} labels={curve.labels} label={t('cokdyby.curve_label', { list: curve.labels.map((l, i) => `${l} ${curve.values[i]}`).join(', ') })} />
					<Text variant="why">{t('cokdyby.curve_note')}</Text>
				</Stack>
			{/if}
			{#if selected}
				<Stack gap={1}>
					<Text variant="caps">{t('cokdyby.words', { region: geo.name(selected) })}{words ? ` · ${t('cokdyby.words_count', { changed: words.changed, total: words.total })}` : ''}</Text>
					{#if !atEnd}
						<Text variant="why">{t('cokdyby.words_end')}</Text>
					{:else if words && words.rows.length}
						<Table head={[{ label: t('cokdyby.words_col_meaning') }, { label: 'A' }, { label: 'B' }]}>
							{#each words.rows as w (w.concept)}
								<Tr>
									<Td>{conceptLabel(w.concept, i18n.locale)}</Td>
									<Td ipa>{w.a}</Td>
									<Td ipa tone={w.differs ? 'red' : undefined}>{w.b}</Td>
								</Tr>
							{/each}
						</Table>
						<Text variant="why">{t('cokdyby.words_why')}</Text>
					{:else}
						<Text variant="why">{t('cokdyby.words_none')}</Text>
					{/if}
				</Stack>
			{/if}
		</Card>

		<Stage label={t('cokdyby.map_a', { year: formatYear(year) })} minHeight={300}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('cokdyby.map_a', { year: formatYear(year) })}
				{summary}
				fill={fillA}
				{hatch}
				edge={edgeA}
				{focus}
				{selected}
				{labels}
				onpick={pick}
			/>
			{#snippet bl()}
				<Floating><Legend items={legend} /></Floating>
			{/snippet}
		</Stage>
		<Stage label={t('cokdyby.map_b', { year: formatYear(year) })} minHeight={300}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('cokdyby.map_b', { year: formatYear(year) })}
				{summary}
				fill={fillB}
				{hatch}
				edge={edgeB}
				{focus}
				{selected}
				{labels}
				onpick={pick}
			/>
			{#snippet br()}
				<Floating tight>
					<Cluster gap={2}>
						{#if focus}<Text variant="small">{t('cokdyby.zoomed')}</Text>{/if}
						<Button variant="quiet" onclick={() => (zoomed = !zoomed)}>{focus ? t('cokdyby.zoom_out') : t('cokdyby.zoom_in')}</Button>
					</Cluster>
				</Floating>
			{/snippet}
		</Stage>
		<Area colSpan={2}>
			<Text variant="why">{t('cokdyby.map_note')}</Text>
		</Area>
	</Screen>
{:else}
	<Screen label={t('cokdyby.none_title')}>
		<Stack gap={3}>
			<Stack gap={1}>
				<Text variant="caps">{t('cokdyby.none_caps')}</Text>
				{#if branch && !resultB && branch.run?.status !== 'failed'}
					<Text variant="h1">{t('cokdyby.running_title')}</Text>
					<Text variant="why">{t('cokdyby.running_note', { pct: Math.round((branch.run?.progress ?? 0) * 100), year: formatYear(branch.run?.year ?? 0) })}</Text>
				{:else}
					<Text variant="h1">{t('cokdyby.none_title')}</Text>
					<Text>{t('cokdyby.none_explain')}</Text>
				{/if}
			</Stack>
			{#if branch?.run?.status === 'failed'}
				<Banner tone="error">{t('cokdyby.failed', { error: branch.run.error ?? '' })}</Banner>
			{/if}
			{#if !branch || branch.run?.status === 'failed'}
				<Stack gap={2}>
					<Text variant="why">{t('cokdyby.none_how')}</Text>
					{#if events.length}
						<Cluster gap={2}>
							<Select
								label={t('cokdyby.event_label')}
								bind:value={pickEvent}
								options={[{ value: -1, label: t('cokdyby.event_pick') }, ...events.map((e) => ({ value: e.value, label: e.label }))]}
							/>
							<Button variant="primary" disabled={!canStart || pickEvent < 0} title={reason || undefined} onclick={start}>{t('cokdyby.start')}</Button>
						</Cluster>
						{#if reason}<Text variant="why">{reason}</Text>{/if}
					{:else}
						<Text variant="why">{t('cokdyby.no_events')}</Text>
					{/if}
				</Stack>
			{/if}
		</Stack>
	</Screen>
{/if}
