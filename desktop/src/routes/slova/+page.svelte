<!-- Slova: tvary jednoho pojmu na mapě vsí v roce časové osy, červené izoglosy tam, kde se tvar mění; karta s tvary
     v největších jazycích a vrtem kraje jako skutečnou historií. V koncovém roce se tvary berou přesně z exportu,
     v dřívějších ze slovníku jazyka v roce (`app.lexicon`), uloženého do cache po rocích a liniích. -->
<script lang="ts">
	import {
		Card,
		Floating,
		Ipa,
		Kbd,
		Legend,
		Screen,
		Select,
		Stack,
		Stage,
		Strata,
		Swatch,
		Table,
		Td,
		Text,
		Tr,
		Button,
		Cluster,
		WorldMap,
		formatYear,
		type EdgeStyle,
		type LegendItem,
		type MapVillage,
		type Stratum
	} from '$lib/ds';
	import { SvelteMap } from 'svelte/reactivity';
	import { i18n, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import { cityMarkers, geography } from '$lib/model/geography';
	import { frameAt, homeLanguage, lineageNames, lineagePalette, speakers } from '$lib/model/languages';
	import { conceptList, formAreas, historyLayers, lineageChain, protoOf, shortMorpheme, villageForms, villageFormsAt } from '$lib/model/slova';
	import { app } from '$lib/state.svelte';

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const endYear = $derived(result?.year ?? 0);
	const year = $derived(Math.min(app.view.year ?? endYear, endYear));
	const atEnd = $derived(year >= endYear);
	const runId = $derived(app.run?.id ?? '');
	const frame = $derived(result ? frameAt(app.frames, year) : null);
	const domainOf = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g.domain])));
	const home = $derived(frame ? homeLanguage(frame.groups, domainOf) : new Map());

	const concepts = $derived(result ? conceptList(result, i18n.locale) : []);
	const concept = $derived(concepts.some((c) => c.value === app.view.concept) ? app.view.concept : (concepts[0]?.value ?? 'water'));
	const word = $derived(conceptLabel(concept, i18n.locale));

	const names = $derived(result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const nameOf = (id: string | null) => (id ? (names.get(id) ?? id) : '—');
	const palette = $derived(result && world ? lineagePalette(world, result) : new Map<string, string>());
	const familyName = (code: string) => world?.languages.find((l) => l.id === code)?.name ?? code;

	// slovníky jazyků v roce: cache rok × linie (klíč nese i běh)
	const lexCache = new SvelteMap<string, Record<string, string> | null>();
	const asked = new Set<string>();
	const lexKey = (lineage: string) => `${runId}|${year}|${lineage}`;
	const lineagesNow = $derived([...new Set([...home.values()].map((h) => h.lineage))]);
	$effect(() => {
		if (atEnd) return;
		for (const l of lineagesNow) {
			const k = lexKey(l);
			if (asked.has(k)) continue;
			asked.add(k);
			void app.lexicon(l, year).then((lex) => lexCache.set(k, lex?.forms ?? null));
		}
	});
	const loading = $derived(!atEnd && lineagesNow.some((l) => !lexCache.has(lexKey(l))));

	const forms = $derived(
		result ? (atEnd ? villageForms(result, home, concept) : villageFormsAt(home, concept, (l) => lexCache.get(lexKey(l)))) : new Map()
	);
	const areas = $derived(formAreas(forms));
	const regionsWithForm = $derived(new Set([...forms.keys()].map((v) => geo?.villages.find((x) => x.id === v)?.region)).size);

	const edge = $derived((a: MapVillage, b: MapVillage): EdgeStyle | null => {
		const fa = forms.get(a.id)?.form, fb = forms.get(b.id)?.form;
		if (fa && fb && fa !== fb) return { color: 'red', width: 1.7 };
		if (a.region !== b.region) return { color: 'muted', width: 0.6, dash: 'dotted', alpha: 0.5 };
		return null;
	});
	const fill = $derived((v: MapVillage) => (forms.has(v.id) ? (palette.get(home.get(v.id)?.lineage ?? '') ?? null) : null));
	const labels = $derived.by(() => {
		if (!geo) return [];
		const out = [];
		if (app.view.region) out.push({ text: geo.name(app.view.region), region: app.view.region, kind: 'strong' as const, dy: -12 });
		return out;
	});
	const markers = $derived(cityMarkers(result));
	const summary = $derived(t('slova.summary', { forms: areas.length, concept: word, regions: regionsWithForm }));

	const legend: LegendItem[] = $derived([
		{ label: t('slova.isogloss_legend'), kind: 'line', color: 'var(--red)' },
		{ label: t('slova.region_border'), kind: 'dashed', color: 'var(--ink-2)' }
	]);

	// největší jazyky: v koncovém roce z exportu (největší domácí skupina linie), jinak ze slovníku jazyka v roce
	const largest = $derived.by(() => {
		if (!frame) return [];
		const spoke = speakers(frame.groups, domainOf);
		const best = new Map<string, { group: string; population: number }>();
		for (const g of frame.groups) {
			const h = domainOf.get(g.id) ?? (g.id.includes('>') ? 'public' : 'home');
			if (h !== 'home' || !g.observed_language) continue;
			const b = best.get(g.observed_language);
			if (!b || g.population > b.population) best.set(g.observed_language, { group: g.id, population: g.population });
		}
		return [...spoke.entries()]
			.sort((a, b) => b[1] - a[1])
			.map(([lineage]) => {
				const entry = atEnd ? result?.lexicon[best.get(lineage)?.group ?? '']?.[concept] : undefined;
				return { lineage, entry, form: atEnd ? entry?.form : lexCache.get(lexKey(lineage))?.[concept] };
			})
			.filter((r) => r.form)
			.slice(0, 6);
	});
	const originLabel = (o: string, loan: boolean) => t(`origin.${loan ? 'loan' : o}` as MessageKey);
	const originOf = (r: { entry?: { origin: string; loan: boolean; language: string } }) =>
		r.entry ? (r.entry.language && r.entry.origin !== 'inherited' ? t('slova.origin_from', { origin: originLabel(r.entry.origin, r.entry.loan), family: familyName(r.entry.language) }) : originLabel(r.entry.origin, r.entry.loan)) : '';

	// vrt kraje: skutečná historie slova v jazyce kraje v roce a v jeho předcích až k protojazyku
	const region = $derived(app.view.region && geo ? geo.regions.find((r) => r.id === app.view.region) : null);
	const regionLineage = $derived.by(() => {
		if (!region || !geo) return null;
		const inRegion = new Set(geo.villages.filter((v) => v.region === region.id).map((v) => v.id));
		let best: { lineage: string; population: number } | null = null;
		for (const [v, h] of home) if (inRegion.has(v) && (!best || h.population > best.population)) best = h;
		return best?.lineage ?? null;
	});
	const chain = $derived.by(() => {
		if (!result || !regionLineage) return [];
		const c = lineageChain(result.lineages, regionLineage);
		return c.length ? c : [regionLineage];
	});
	const histCache = new SvelteMap<string, { year: number; form: string | null }[]>();
	const histAsked = new Set<string>();
	const histKey = (lineage: string) => `${runId}|${lineage}|${concept}`;
	$effect(() => {
		for (const l of chain) {
			const k = histKey(l);
			if (histAsked.has(k)) continue;
			histAsked.add(k);
			void app.wordHistory(l, concept).then((h) => histCache.set(k, h));
		}
	});
	const histLoading = $derived(chain.some((l) => !histCache.has(histKey(l))));
	const layers = $derived.by(() => {
		if (!result || !chain.length || histLoading) return [];
		const code = protoOf(result, chain[chain.length - 1]);
		const form = code ? result.proto_lexicon?.[code]?.forms[concept] : null;
		const start = world?.start_year ?? app.run?.start_year ?? 0;
		return historyLayers(
			chain.map((id) => ({ id, history: histCache.get(histKey(id)) ?? [] })),
			code ? { language: code, form: form ?? null, year: start } : null,
			year
		);
	});
	const strata: Stratum[] = $derived(
		layers.map((l) => ({
			form: l.proto ? `*${l.form}` : l.form,
			note: [formatYear(l.year), l.proto ? t('slova.proto_note', { language: familyName(l.language) }) : nameOf(l.language), l.changed ? t('slova.core_switch') : '']
				.filter(Boolean)
				.join(' · '),
			changed: l.changed
		}))
	);
	// protoformy pojmu ve všech protojazycích zadání
	const protoForms = $derived(
		Object.entries(result?.proto_lexicon ?? {})
			.map(([id, l]) => ({ id, form: l.forms[concept] }))
			.filter((p) => p.form)
	);
	const pick = (r: string) => (app.view.region = r);
	const setConcept = (c: string) => (app.view.concept = c);
</script>

{#if !world || !geo}
	<Screen><Text variant="why">{t('check.running')}</Text></Screen>
{:else if !result || !frame || !concepts.length}
	<Screen><Stack gap={3}><Text variant="h1">{t('shell.nav.slova')}</Text><Text variant="why">{t('slova.empty')}</Text></Stack></Screen>
{:else}
	<Screen columns={['fill', 380]} label={t('slova.title', { concept: word })}>
		<Stage label={t('slova.map', { concept: word, year: formatYear(year) })}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('slova.map', { concept: word, year: formatYear(year) })}
				{summary}
				{fill}
				fillAlpha={0.4}
				{edge}
				selected={app.view.region}
				{labels}
				{markers}
				onpick={pick}
			/>
			{#snippet tl()}
				<Floating>
					<Text variant="caps">{t('slova.word')}</Text>
					<Text variant="big">{word.toUpperCase()}</Text>
					{#if protoForms.length}
						<Cluster gap={2} align="baseline" label={t('slova.proto_forms')}>
							{#each protoForms as p (p.id)}
								<Cluster gap={1} align="baseline"><Ipa text={`*${p.form}`} size="m" /><Text variant="small" as="span">{p.id}.</Text></Cluster>
							{/each}
						</Cluster>
					{/if}
					{#each areas.slice(0, 4) as a (a.form)}
						<Cluster gap={2} align="baseline">
							{#if a.foreign}<i><Ipa text={a.form} size="m" /></i>{:else}<Ipa text={a.form} size="m" />{/if}
							<Text variant="small" as="span">{t('slova.form_count', { n: a.villages })}</Text>
						</Cluster>
					{/each}
					{#if areas.length > 4}<Text variant="small">{t('slova.more_forms', { n: areas.length - 4 })}</Text>{/if}
				</Floating>
			{/snippet}
			{#snippet tr()}
				<Floating>
					<Cluster gap={2} align="center">
						<Text variant="caps">{t('slova.concept')}</Text>
						<Select label={t('slova.concept')} value={concept} options={concepts} onchange={setConcept} />
					</Cluster>
				</Floating>
			{/snippet}
			{#snippet bl()}
				<Floating>
					<Legend items={legend}>{t('slova.italic_legend')} · {t('slova.forms_count', { forms: areas.length, villages: forms.size })}</Legend>
				</Floating>
			{/snippet}
			{#snippet br()}
				<Floating><Text variant="small"><Kbd>←</Kbd><Kbd>→</Kbd> {t('slova.keys')}</Text></Floating>
			{/snippet}
		</Stage>

		<Card label={word}>
			<Stack gap={1}>
				<Text variant="caps">{t('slova.word')}</Text>
				<Text variant="h1">‘{word}’</Text>
				{#if !atEnd}<Text variant="why">{t('slova.end_only', { year: formatYear(year) })}</Text>{/if}
			</Stack>
			<Stack gap={1}>
				<Text variant="caps">{t('slova.largest', { year: formatYear(year) })}</Text>
				<Table head={[{ label: t('slova.col.language') }, { label: t('slova.col.form') }, { label: t('slova.col.origin') }]}>
					{#each largest as r (r.lineage)}
						<Tr>
							<Td><Swatch color={palette.get(r.lineage) ?? 'var(--ink-3)'} />{nameOf(r.lineage)}</Td>
							<Td><Ipa text={r.form ?? ''} size="m" /></Td>
							<Td><Text variant="why" as="span">{originOf(r)}</Text></Td>
						</Tr>
					{/each}
				</Table>
				<Text variant="why">{loading ? t('slova.loading') : t('slova.origin_note')}</Text>
			</Stack>
			<Stack gap={1}>
				{#if region}
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t('slova.core_caps', { region: region.name })}</Text>
						<Button variant="quiet" onclick={() => (app.view.region = null)}>{t('slova.clear')}</Button>
					</Cluster>
					<Text variant="why">{t('slova.core_hint')}</Text>
					{#if histLoading}
						<Text variant="why">{t('slova.loading')}</Text>
					{:else if strata.length}
						<Strata items={strata} label={t('slova.core_caps', { region: region.name })} />
					{:else}
						<Text variant="why">{t('slova.no_form')}</Text>
					{/if}
				{:else}
					<Text variant="caps">{t('slova.core')}</Text>
					<Text variant="why">{t('slova.core_pick')}</Text>
				{/if}
			</Stack>
		</Card>
	</Screen>
{/if}
