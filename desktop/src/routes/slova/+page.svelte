<!-- Slova: tvary jednoho pojmu na mapě vsí, červené izoglosy tam, kde se tvar mění; karta s tvary v největších
     jazycích a vrtem kraje. Slovník nese jen koncový export, proto mapa ukazuje koncový snímek. -->
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
	import { i18n, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import { cityMarkers, geography } from '$lib/model/geography';
	import { frameAt, homeLanguage, lineageNames, lineagePalette, speakers } from '$lib/model/languages';
	import { conceptList, formAreas, shortMorpheme, villageForms } from '$lib/model/slova';
	import { app } from '$lib/state.svelte';

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const year = $derived(result?.year ?? 0);
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

	const forms = $derived(result ? villageForms(result, home, concept) : new Map());
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

	// největší jazyky: lineage → největší domácí skupina
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
			.map(([lineage]) => ({ lineage, entry: result?.lexicon[best.get(lineage)?.group ?? '']?.[concept], group: best.get(lineage)?.group }))
			.filter((r) => r.entry)
			.slice(0, 6);
	});
	const originLabel = (o: string, loan: boolean) => t(`origin.${loan ? 'loan' : o}` as MessageKey);
	const originOf = (r: { entry?: { origin: string; loan: boolean; language: string } }) =>
		r.entry ? (r.entry.language && r.entry.origin !== 'inherited' ? t('slova.origin_from', { origin: originLabel(r.entry.origin, r.entry.loan), family: familyName(r.entry.language) }) : originLabel(r.entry.origin, r.entry.loan)) : '';

	// vrt kraje: tvary ve vsích kraje podle koncového exportu
	const region = $derived(app.view.region && geo ? geo.regions.find((r) => r.id === app.view.region) : null);
	const strata: Stratum[] = $derived.by(() => {
		if (!region || !geo) return [];
		const inRegion = new Set(geo.villages.filter((v) => v.region === region.id).map((v) => v.id));
		const rows: Stratum[] = [];
		const seen = new Set<string>();
		for (const [, f] of [...forms.entries()].filter(([v]) => inRegion.has(v)).sort((a, b) => a[0].localeCompare(b[0]))) {
			const key = `${f.form}|${f.lineage}`;
			if (seen.has(key)) continue;
			seen.add(key);
			const e = f.entry;
			const bits = [nameOf(f.lineage)];
			if (e.origin !== 'inherited' || e.loan) bits.push(originOf({ entry: e }));
			if (e.base) bits.push(t('slova.core_base', { base: shortMorpheme(e.base) ?? '' }));
			else if (e.root) bits.push(t('slova.core_root', { root: shortMorpheme(e.root) ?? '' }));
			rows.push({ form: f.form, note: bits.join(' · '), changed: e.origin !== 'inherited' || e.loan });
		}
		return rows;
	});
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
				{#if app.view.year != null && app.view.year !== year}<Text variant="why">{t('slova.end_only', { year: formatYear(year) })}</Text>{/if}
			</Stack>
			<Stack gap={1}>
				<Text variant="caps">{t('slova.largest', { year: formatYear(year) })}</Text>
				<Table head={[{ label: t('slova.col.language') }, { label: t('slova.col.form') }, { label: t('slova.col.origin') }]}>
					{#each largest as r (r.lineage)}
						<Tr>
							<Td><Swatch color={palette.get(r.lineage) ?? 'var(--ink-3)'} />{nameOf(r.lineage)}</Td>
							<Td><Ipa text={r.entry?.form ?? ''} size="m" /></Td>
							<Td><Text variant="why" as="span">{originOf(r)}</Text></Td>
						</Tr>
					{/each}
				</Table>
				<Text variant="why">{t('slova.origin_note')}</Text>
			</Stack>
			<Stack gap={1}>
				{#if region}
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t('slova.core_caps', { region: region.name })}</Text>
						<Button variant="quiet" onclick={() => (app.view.region = null)}>{t('slova.clear')}</Button>
					</Cluster>
					<Text variant="why">{t('slova.core_hint')}</Text>
					{#if strata.length}
						<Strata items={strata} label={t('slova.core_caps', { region: region.name })} />
					{:else}
						<Text variant="why">{t('slova.no_form')}</Text>
					{/if}
					<Text variant="why">{t('slova.core_pending')}</Text>
				{:else}
					<Text variant="caps">{t('slova.core')}</Text>
					<Text variant="why">{t('slova.core_pick')}</Text>
				{/if}
			</Stack>
		</Card>
	</Screen>
{/if}
