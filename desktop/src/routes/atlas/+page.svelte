<!-- Atlas: mapa vsí obarvená jazykem doma v roce časové osy, vrstvy států, veřejné řeči, písma
     a věrnosti; karta vybraného kraje. Během běhu ukazuje průběh (stav Běh). -->
<script lang="ts">
	import {
		Bars,
		Button,
		Card,
		Checkbox,
		Cluster,
		Disclosure,
		Floating,
		Ipa,
		Kbd,
		Ledger,
		LedgerRow,
		Legend,
		Screen,
		Segmented,
		Stack,
		Stage,
		Swatch,
		Table,
		Td,
		Text,
		Tr,
		WorldMap,
		familyColor,
		formatYear,
		languagePalette,
		type BarRow,
		type EdgeStyle,
		type LegendItem,
		type MapVillage
	} from '$lib/ds';
	import { causeMessage, nameHistory, type NameHistory } from '$lib/model/jmena';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { languageLabels, regionGroups } from '$lib/model/atlas';
	import { conceptLabel } from '$lib/model/concepts';
	import { cityMarkers, geography } from '$lib/model/geography';
	import { frameAt, homeLanguage, lineageFamilies, lineageNames, lineagePalette, shownLineage, speakers, varietiesAt } from '$lib/model/languages';
	import { romanize } from '$lib/naming';
	import { app } from '$lib/state.svelte';

	type Layer = 'lang' | 'state' | 'public' | 'literacy' | 'loyalty';
	let layer = $state<Layer>('lang');

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const endYear = $derived(result?.year ?? app.run?.end_year ?? world?.end_year ?? 0);
	const year = $derived(app.view.year ?? (app.running ? Math.round(app.run?.year ?? 0) : endYear));
	const atEnd = $derived(!!result && year >= result.year);
	const frame = $derived(frameAt(app.frames, year));
	const domainOf = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g.domain])));
	const homeRaw = $derived(frame ? homeLanguage(frame.groups, domainOf) : new Map());
	const spokenRaw = $derived(frame ? speakers(frame.groups, domainOf) : new Map<string, number>());
	// malé jazyky jako variety příbuzného jazyka (přepínač „všechny jazyky“ ukáže stav enginu)
	const varieties = $derived(result && world && frame ? varietiesAt(world, result, frame.groups, domainOf) : null);
	const shown = (id: string) => shownLineage(varieties, id, app.view.allLanguages);
	const home = $derived(new Map([...homeRaw].map(([v, h]) => [v, { ...h, lineage: shown(h.lineage) }])));
	const spoken = $derived.by(() => {
		const out = new Map<string, number>();
		for (const [id, n] of spokenRaw) out.set(shown(id), (out.get(shown(id)) ?? 0) + n);
		return out;
	});

	// jména a barvy: z výsledku; během běhu z vlastních jmen ve snímku
	const names = $derived.by(() => {
		if (result && geo) return lineageNames(result, geo.name, i18n.locale, app.frames);
		const out = new Map<string, string>();
		for (const f of app.frames) for (const [id, e] of Object.entries(f.endonyms)) if (e) out.set(id, romanize(e));
		return out;
	});
	const nameOf = (id: string | null) => (id ? (names.get(id) ?? id) : '—');
	/** jméno jazyka skupiny; malý jazyk jako „X (varieta Y)“ */
	const groupLanguage = (id: string | null) => {
		if (!id) return '—';
		const host = shown(id);
		return host !== id ? t('shell.variety_of', { name: nameOf(id), host: nameOf(host) }) : nameOf(id);
	};
	const palette = $derived.by(() => {
		if (result && world) return lineagePalette(world, result);
		const ids = [...new Set(app.frames.flatMap((f) => Object.keys(f.languages)))];
		return languagePalette(ids.map((id, i) => ({ id, start: i })));
	});
	const families = $derived(world && result ? lineageFamilies(world, result) : new Map<string, number>());
	const familyIndex = (code: string) => Math.max(0, world?.languages.findIndex((l) => l.id === code) ?? 0);
	const familyName = (code: string) => world?.languages.find((l) => l.id === code)?.name ?? code;

	// státy ve snímku a jejich politika z výsledku
	const stateOf = $derived(new Map((frame?.states ?? []).flatMap((s, n) => s.regions.map((r) => [r, { ...s, n }] as const))));
	const policyOf = $derived(new Map((result?.states ?? []).map((s) => [s.id, s.policy])));
	const groupById = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g])));

	const fill = $derived.by(() => {
		if (layer === 'lang') return (v: MapVillage) => palette.get(home.get(v.id)?.lineage ?? '') ?? null;
		if (layer === 'public')
			return (v: MapVillage) => {
				const pub = frame?.census[v.region]?.public ?? {};
				const top = Object.entries(pub).sort((a, b) => b[1] - a[1])[0];
				return top ? familyColor(familyIndex(top[0])) : null;
			};
		return undefined;
	});
	const fillAlpha = $derived(layer === 'public' ? 0.4 : 0.55);
	const regionFill = $derived(
		layer === 'state'
			? (r: { id: string }) => {
					const s = stateOf.get(r.id);
					if (!s) return null;
					const pol = policyOf.get(s.id);
					return { color: 'ink', alpha: pol === 'enforced' ? 0.16 : pol === 'promoted' ? 0.08 : 0.03 };
				}
			: undefined
	);
	const regionHatch = $derived(
		layer === 'state'
			? (r: { id: string }) => {
					const s = stateOf.get(r.id);
					return s ? { angle: [0.6, -0.6, 1.4, 0.2][s.n % 4], color: 'muted', gap: 7, width: 0.6 } : null;
				}
			: undefined
	);
	// písmo a věrnost: jen koncový snímek (hodnoty skupin z exportu)
	const hatch = $derived(
		(layer === 'literacy' || layer === 'loyalty') && atEnd
			? (v: MapVillage) => {
					const g = groupById.get(home.get(v.id)?.group ?? '');
					const value = g ? (layer === 'literacy' ? g.literacy : g.loyalty) : 0;
					return value > 0.05 ? { angle: Math.PI / 4, color: 'ink', gap: Math.max(3, 12 - value * 10), width: 0.7 } : null;
				}
			: undefined
	);
	const edge = $derived.by(() => {
		return (a: MapVillage, b: MapVillage): EdgeStyle | null => {
			const sa = stateOf.get(a.region)?.id, sb = stateOf.get(b.region)?.id;
			if (a.region !== b.region && sa !== sb) return { color: 'ink', width: layer === 'state' ? 1.5 : 1.1, dash: 'state' };
			if (layer === 'lang' && home.get(a.id)?.lineage !== home.get(b.id)?.lineage) return { color: 'ink', width: 0.9, alpha: 0.7 };
			if (a.region !== b.region) return { color: 'muted', width: 0.6, dash: 'dotted', alpha: 0.6 };
			return null;
		};
	});

	const many = $derived((geo?.regions.length ?? 0) > 40);
	const labels = $derived.by(() => {
		if (!geo || !world) return [];
		const out = [];
		if (app.view.region) out.push({ text: geo.name(app.view.region), region: app.view.region, kind: 'strong' as const, dy: -12 });
		if (layer === 'lang') out.push(...languageLabels(home, (id) => nameOf(id), many ? 4 : 1));
		if (layer === 'state') out.push(...(frame?.states ?? []).map((s) => ({ text: s.name, region: s.regions[0], kind: 'state' as const, dy: 16 })));
		for (const r of world.regions) if (!many || (r.city ?? 0) > 0) out.push({ text: geo.name(r.id), region: r.id, kind: 'region' as const, dy: -10 });
		return out;
	});
	const markers = $derived(cityMarkers(result));

	// legenda
	const legend: LegendItem[] = $derived.by(() => {
		if (!world) return [];
		if (layer === 'lang') {
			const count = new Map<number, number>();
			for (const id of new Set([...home.values()].map((h) => h.lineage))) {
				const f = families.get(id) ?? 0;
				count.set(f, (count.get(f) ?? 0) + 1);
			}
			return [
				...world.languages.map((l, i) => ({ label: t('atlas.family', { name: l.name ?? l.id, n: count.get(i) ?? 0 }), color: familyColor(i) })),
				{ label: t('atlas.city'), kind: 'square' as const }
			];
		}
		if (layer === 'state') return [{ label: t('atlas.state_border'), kind: 'dashed' as const }, { label: t('atlas.policy'), kind: 'hatch' as const, color: 'var(--ink-2)' }];
		if (layer === 'public') return world.languages.map((l, i) => ({ label: l.name ?? l.id, color: familyColor(i) }));
		return [{ label: t('atlas.share'), kind: 'hatch' as const, color: 'var(--ink)' }];
	});

	// karta kraje
	const region = $derived(app.view.region && geo ? geo.regions.find((r) => r.id === app.view.region) : null);
	const toponym = $derived(region ? result?.onomastics?.toponyms?.[region.id] : undefined);
	const history = $derived(region ? nameHistory(result?.names, `territory:${region.id}`) : null);
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
	const census = $derived(region && frame ? frame.census[region.id] : undefined);
	const censusBars: BarRow[] = $derived.by(() => {
		if (!census) return [];
		const row = (label: string, shares: Record<string, number>) => {
			const sorted = Object.entries(shares).sort((a, b) => b[1] - a[1]);
			return { label, segments: sorted.map(([code, v]) => ({ value: v, color: familyColor(familyIndex(code)), label: familyName(code) })), value: sorted.map(([, v]) => Math.round(v * 100)).join(' : ') };
		};
		return [row(t('atlas.home'), census.home), row(t('atlas.public'), census.public)];
	});
	const groups = $derived(region && frame && geo ? regionGroups(frame, geo.villages, region.id, domainOf) : new Map());
	const WORDS = ['water', 'stone', 'fire', 'person'];
	// slova místa: v koncovém roce s původem z exportu; jinak slovník jazyka v roce ze složky běhu
	const endWords = $derived.by(() => {
		if (!result || !region || !atEnd) return [];
		const best = [...groups.values()].flat().sort((a, b) => b.population - a.population)[0];
		const lex = best ? result.lexicon[best.group] : undefined;
		return lex ? WORDS.filter((c) => lex[c]).map((c) => ({ concept: c, form: lex[c].form, origin: (lex[c].loan ? 'loan' : lex[c].origin) as string | null })) : [];
	});
	let yearWords = $state<{ concept: string; form: string; origin: string | null }[]>([]);
	$effect(() => {
		const best = region && !atEnd ? [...groups.values()].flat().sort((a, b) => b.population - a.population)[0] : null;
		const lineage = best?.lineage;
		yearWords = [];
		if (!lineage) return;
		void app.lexicon(lineage, year).then((lex) => {
			yearWords = lex ? WORDS.filter((c) => lex.forms[c]).map((c) => ({ concept: c, form: lex.forms[c], origin: null })) : [];
		});
	});
	const words = $derived(atEnd ? endWords : yearWords);
	const villageName = (id: string) => result?.onomastics?.toponyms?.[id]?.name ?? id;

	// přehled bez výběru a stav běhu
	const top: BarRow[] = $derived.by(() => {
		const list = [...spoken.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6), max = list[0]?.[1] ?? 1;
		return list.map(([id, n]) => ({ label: nameOf(id), segments: [{ value: n / max, color: palette.get(id) ?? 'var(--ink-2)' }], value: number(n) }));
	});
	const people = $derived([...spoken.values()].reduce((a, b) => a + b, 0));
	const summary = $derived(
		geo && frame ? t('atlas.summary', { villages: geo.villages.length, year: formatYear(year), langs: Object.keys(frame.languages).length, families: world?.languages.length ?? 0 }) : ''
	);
	const pick = (r: string) => (app.view.region = r);
</script>

{#snippet nameHistoryBlock(h: NameHistory | null)}
	{#if h?.current}
		{@const cur = h.current}
		<Disclosure>
			{#snippet summary()}{t('name.history')} · {t('name.current', { name: cur.name, year: formatYear(cur.founded) })}{/snippet}
			<Stack gap={2}>
				<Ledger termWidth={110}>
					<LedgerRow term={t('name.motivation')}
						>{motivation(cur.motivation)}{#if cur.meaning} <Text variant="why" as="span">{t('jmena.meaning', { meaning: cur.meaning })}</Text>{/if}</LedgerRow
					>
					{#each cur.timeline as step, i (i)}
						<LedgerRow term={formatYear(step.year)}><Ipa text={step.ipa} /> {step.name} <Text variant="why" as="span">{causeText(step.cause)}</Text></LedgerRow>
					{/each}
				</Ledger>
				{#if h.earlier.length}
					<Text variant="caps">{t('name.earlier')}</Text>
					<Ledger termWidth={110}>
						{#each h.earlier as r (r.id)}
							<LedgerRow term={t('name.ended', { from: formatYear(r.founded), to: r.ended != null ? formatYear(r.ended) : '…' })}
								>{r.name} <Ipa text={r.ipa} /> <Text variant="why" as="span">{motivation(r.motivation)}</Text></LedgerRow
							>
						{/each}
					</Ledger>
				{/if}
				{#if h.exonyms.length}
					<Text variant="caps">{t('name.exonyms')}</Text>
					<Ledger termWidth={110}>
						{#each h.exonyms as e (e.lineage)}
							<LedgerRow term={exonymSpeaker(e.lineage)}>{e.record.name} <Ipa text={e.record.ipa} /></LedgerRow>
						{/each}
					</Ledger>
				{/if}
			</Stack>
		</Disclosure>
	{/if}
{/snippet}

{#if !world || !geo}
	<Screen><Text variant="why">{t('check.running')}</Text></Screen>
{:else if !frame}
	<Screen><Stack gap={3}><Text variant="h1">{t('shell.nav.atlas')}</Text><Text variant="why">{t('atlas.empty')}</Text></Stack></Screen>
{:else}
	<Screen columns={['fill', 370]} label={t('atlas.title', { year: formatYear(year) })}>
		<Stage label={t('atlas.map', { year: formatYear(year) })}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('atlas.map', { year: formatYear(year) })}
				{summary}
				{fill}
				{fillAlpha}
				{regionFill}
				{regionHatch}
				{hatch}
				{edge}
				selected={app.view.region}
				{labels}
				{markers}
				onpick={pick}
			/>
			{#snippet tr()}
				<Floating tight>
					<Segmented
						label={t('atlas.layer')}
						bind:value={layer}
						options={(['lang', 'state', 'public', 'literacy', 'loyalty'] as const).map((l) => ({ value: l, label: t(`atlas.layer.${l}` as MessageKey) }))}
					/>
				</Floating>
			{/snippet}
			{#snippet bl()}
				<Floating>
					<Legend items={legend}>
						{#if layer === 'lang' && palette.size > 8}{t('atlas.shade_note')}{/if}
						{#if layer === 'lang' && varieties}
							<Checkbox bind:checked={app.view.allLanguages} meta={t('atlas.small_count', { n: varieties.host.size + varieties.orphans.length })}>{t('shell.all_languages')}</Checkbox>
						{/if}
						{#if (layer === 'literacy' || layer === 'loyalty') && !atEnd}{t('atlas.end_only')}{/if}
					</Legend>
				</Floating>
			{/snippet}
			{#snippet br()}
				<Floating><Text variant="small"><Kbd>←</Kbd><Kbd>→</Kbd> {t('atlas.keys')}</Text></Floating>
			{/snippet}
		</Stage>

		{#if app.running && app.run}
			<Card label={t('atlas.run_title')}>
				<Stack gap={1}>
					<Text variant="caps">{t('atlas.run_caps', { from: formatYear(app.run.start_year), to: formatYear(app.run.end_year) })}</Text>
					<Text variant="h1">{t('atlas.run_title')}</Text>
					<Text variant="why">{t('atlas.run_note')}</Text>
				</Stack>
				<Ledger>
					<LedgerRow term={t('atlas.run_done')}>{t('atlas.run_done_value', { done: Math.round(app.run.year - app.run.start_year), total: app.run.end_year - app.run.start_year })}</LedgerRow>
					<LedgerRow term={t('atlas.run_now')}
						>{t('atlas.run_now_value', { langs: Object.keys(frame.languages).length, dialects: frame.dialects.length, states: frame.states.length, people: number(people) })}</LedgerRow
					>
				</Ledger>
				<Bars rows={top} label={t('atlas.top')} />
			</Card>
		{:else if region}
			<Card label={region.name}>
				<Stack gap={1}>
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t('atlas.region_caps', { state: stateOf.get(region.id)?.name ?? t('atlas.no_state'), year: formatYear(year) })}</Text>
						<Button variant="quiet" onclick={() => (app.view.region = null)}>{t('atlas.clear')}</Button>
					</Cluster>
					<Text variant="h1">{region.name}</Text>
					{#if toponym}<Text><Ipa text={toponym.ipa} slashes /> <Text variant="why" as="span">{t('atlas.meaning', { meaning: toponym.meaning })}</Text></Text>{/if}
				</Stack>
				{@render nameHistoryBlock(history)}
				<Button variant="quiet" href="/jmena">{t('name.generate_here')}</Button>
				{#if censusBars.length}
					<Stack gap={2}>
						<Text variant="caps">{t('atlas.census')}</Text>
						<Bars rows={censusBars} labelWidth={100} />
						<Text variant="why">{t('atlas.census_note')}</Text>
					</Stack>
				{/if}
				<Stack gap={1}>
					<Text variant="caps">{t('atlas.villages')}</Text>
					<Table head={[{ label: t('atlas.col.village') }, { label: t('atlas.col.language') }, { label: t('atlas.col.people'), num: true }]}>
						{#each [...groups.entries()] as [village, list] (village)}
							{#each list as g, i (g.group)}
								<Tr>
									<Td>{i === 0 ? villageName(village) : ''}</Td>
									<Td><Swatch color={palette.get(shown(g.lineage ?? '')) ?? 'var(--ink-3)'} />{groupLanguage(g.lineage)}</Td>
									<Td num>{number(g.population)}</Td>
								</Tr>
							{/each}
						{/each}
					</Table>
				</Stack>
				<Stack gap={1}>
					<Text variant="caps">{t('atlas.words')}</Text>
					{#if words.length}
						<Ledger termWidth={90}>
							{#each words as w (w.concept)}<LedgerRow term={conceptLabel(w.concept, i18n.locale)}><Ipa text={w.form} size="m" />{#if w.origin} <Text variant="why" as="span">{t(`origin.${w.origin}` as MessageKey)}</Text>{/if}</LedgerRow>{/each}
						</Ledger>
						<Button variant="quiet" href="/slova">{t('atlas.all_words')}</Button>
					{:else}
						<Text variant="why">{t('atlas.words_end')}</Text>
					{/if}
				</Stack>
			</Card>
		{:else}
			{@const overview = varieties && !app.view.allLanguages
				? t('atlas.overview_var', { langs: varieties.major.length, small: varieties.host.size + varieties.orphans.length, year: formatYear(year) })
				: t('atlas.overview', { langs: Object.keys(frame.languages).length, year: formatYear(year) })}
			<Card label={overview}>
				<Stack gap={1}>
					<Text variant="caps">{world.name ?? ''} · {formatYear(year)}</Text>
					<Text variant="h1">{overview}</Text>
					<Text variant="why">{t('atlas.overview_hint')}</Text>
				</Stack>
				<Stack gap={2}>
					<Text variant="caps">{t('atlas.top')}</Text>
					<Bars rows={top} />
				</Stack>
			</Card>
		{/if}
	</Screen>
{/if}
