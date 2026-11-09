<!-- Svět: nastavení světa, mapa krajů (jazyk na počátku) a karta vybraného kraje s úpravou.
     Úpravy jdou přes app.edit (Zpět/Znovu). Kreslení krajů zatím není, proto tu není ani jako ovládání. -->
<script lang="ts">
	import {
		Button,
		Card,
		Checkbox,
		Chip,
		Cluster,
		Field,
		Floating,
		Ipa,
		Kbd,
		Legend,
		Screen,
		Segmented,
		Stack,
		Stage,
		Text,
		TextInput,
		WorldMap,
		familyColor,
		type LegendItem,
		type MapLabel,
		type MapMarker,
		type MapVillage
	} from '$lib/ds';
	import { t, type MessageKey } from '$lib/i18n.svelte';
	import { geography } from '$lib/model/geography';
	import { cityOptions, hasCity, levelsInOrder, regionsPerLanguage, worldWarnings } from '$lib/model/svet';
	import { app } from '$lib/state.svelte';

	const world = $derived(app.world);
	const geo = $derived(world ? geography(world, app.result) : null);
	const levels = $derived(app.schema?.levels as Record<string, string[]> | undefined);
	const backgrounds = $derived(levelsInOrder(levels?.background_levels, ['none', 'calm', 'normal', 'turbulent']));
	const terrains = $derived(levelsInOrder(levels?.terrain_access, ['plain', 'hills', 'mountains', 'island']));
	const identities = $derived(levelsInOrder(levels?.identity_loyalty, ['distinct', 'shared', 'strong']));

	const langIndex = $derived(new Map((world?.languages ?? []).map((l, i) => [l.id, i])));
	const perLang = $derived(world ? regionsPerLanguage(world) : new Map<string, number>());
	const warnings = $derived(world ? worldWarnings(world) : []);
	const cityCount = $derived((world?.regions ?? []).filter(hasCity).length);

	const region = $derived(app.view.region && world ? (world.regions.find((r) => r.id === app.view.region) ?? null) : null);
	const toponym = $derived(region ? app.result?.onomastics?.toponyms?.[region.id] : undefined);

	// ---- mapa
	const regionById = $derived(new Map((world?.regions ?? []).map((r) => [r.id, r])));
	const fill = $derived((v: MapVillage) => {
		const lang = regionById.get(v.region)?.language;
		const i = lang ? langIndex.get(lang) : undefined;
		return i === undefined ? null : familyColor(i);
	});
	const edge = $derived((a: MapVillage, b: MapVillage) => {
		if (a.region === b.region) return null;
		const la = regionById.get(a.region)?.language, lb = regionById.get(b.region)?.language;
		return la !== lb ? { color: 'ink' as const, width: 0.9, alpha: 0.7 } : { color: 'muted' as const, width: 0.6, dash: 'dotted' as const, alpha: 0.6 };
	});
	const markers: MapMarker[] = $derived((world?.regions ?? []).filter(hasCity).map((r) => ({ region: r.id, kind: 'city' as const })));
	const labels: MapLabel[] = $derived.by(() => {
		if (!world || !geo) return [];
		const out: MapLabel[] = world.regions.filter((r) => hasCity(r) && r.id !== app.view.region).map((r) => ({ text: geo.name(r.id), region: r.id, kind: 'region' as const, dy: -10 }));
		if (app.view.region) out.push({ text: geo.name(app.view.region), region: app.view.region, kind: 'strong' as const, dy: -12 });
		return out;
	});
	const legend: LegendItem[] = $derived([
		...(world?.languages ?? []).map((l, i) => ({ label: t('svet.legend_langs', { name: l.name ?? l.id, n: perLang.get(l.id) ?? 0 }), color: familyColor(i) })),
		{ label: t('svet.legend_city'), kind: 'square' as const }
	]);
	const summary = $derived(world ? t('svet.map_summary', { regions: world.regions.length, langs: world.languages.length }) : '');

	// upozornění ukázaná na mapě
	let shown = $state<string | null>(null);
	const highlight = $derived(warnings.find((w) => w.kind === shown)?.regions ?? []);

	// ---- úpravy zadání
	const num = (v: string | number, fallback: number) => (Number.isFinite(Number(v)) && String(v).trim() !== '' ? Number(v) : fallback);
	let seed = $state<string | number>(1), startYear = $state<string | number>(0), endYear = $state<string | number>(0), spacing = $state<string | number>(10);
	let nameDraft = $state('');
	$effect(() => {
		if (!world) return;
		seed = world.seed ?? 1;
		startYear = world.start_year ?? 0;
		endYear = world.end_year;
		spacing = (world.village_spacing as number | undefined) ?? 10;
	});
	$effect(() => {
		nameDraft = region && geo ? geo.name(region.id) : '';
	});

	const commitNumber = (key: 'seed' | 'start_year' | 'end_year' | 'village_spacing', label: string, v: string | number) => {
		if (!world) return;
		const next = num(v, NaN);
		if (!Number.isFinite(next) || (key === 'village_spacing' && next <= 0) || (key === 'seed' && !Number.isInteger(next))) {
			seed = world.seed ?? 1; startYear = world.start_year ?? 0; endYear = world.end_year; spacing = (world.village_spacing as number | undefined) ?? 10;
			return;
		}
		if (world[key] === next) return;
		app.edit(label, (w) => {
			w[key] = next;
		});
	};
	const setRegion = <K extends 'language' | 'terrain' | 'identity' | 'city'>(id: string, key: K, label: string, value: string | number) => {
		app.edit(label, (w) => {
			const r = w.regions.find((x) => x.id === id);
			if (r) (r as Record<string, unknown>)[key] = value;
		});
	};
	const rename = () => {
		if (!region || !geo) return;
		const next = nameDraft.trim();
		if (!next || next === geo.name(region.id)) {
			nameDraft = geo.name(region.id);
			return;
		}
		const id = region.id;
		app.edit(t('svet.edit.name', { name: next }), (w) => {
			const r = w.regions.find((x) => x.id === id);
			if (r) r.name = next;
		});
	};
	const pick = (id: string) => (app.view.region = id);
</script>

{#if !world || !geo}
	<Screen><Stack gap={3}><Text variant="h1">{t('svet.title')}</Text><Text variant="why">{t('svet.empty_world')}</Text></Stack></Screen>
{:else}
	<Screen columns={[250, 'fill', 360]} label={t('svet.title')}>
		<Card label={t('svet.settings')}>
			<Stack gap={3}>
				<Text variant="caps">{t('svet.settings')}</Text>
				<Field label={t('svet.seed')}>
					<TextInput type="number" width="s" label={t('svet.edit.seed')} bind:value={seed} onchange={(v) => commitNumber('seed', t('svet.edit.seed'), v)} />
				</Field>
				<Field label={t('svet.years')} hint={t('svet.years_note', { step: (world.generation_years as number | undefined) ?? 25 })}>
					<Cluster gap={2}>
						<TextInput type="number" width="s" label={t('svet.edit.start')} bind:value={startYear} onchange={(v) => commitNumber('start_year', t('svet.edit.start'), v)} />
						<Text as="span" tone="muted">–</Text>
						<TextInput type="number" width="s" label={t('svet.edit.end')} bind:value={endYear} onchange={(v) => commitNumber('end_year', t('svet.edit.end'), v)} />
					</Cluster>
				</Field>
				<Field label={t('svet.background')} hint={t('svet.background_note')}>
					<Segmented
						label={t('svet.edit.background')}
						value={(world.background as string | undefined) ?? 'none'}
						options={backgrounds.map((b) => ({ value: b, label: t(`svet.background.${b}` as MessageKey) }))}
						onchange={(v) => app.edit(t('svet.edit.background'), (w) => (w.background = v))}
					/>
				</Field>
				<Field label={t('svet.spacing')} hint={t('svet.spacing_note')}>
					<Cluster gap={2}>
						<TextInput type="number" width="s" step={0.5} min={0.5} label={t('svet.edit.spacing')} bind:value={spacing} onchange={(v) => commitNumber('village_spacing', t('svet.edit.spacing'), v)} />
						<Text as="span" tone="muted">km</Text>
					</Cluster>
				</Field>
				<Field hint={t('svet.semantics_note')}>
					<Checkbox checked={world.semantics !== false} onchange={(c) => app.edit(t('svet.edit.semantics'), (w) => (w.semantics = c))}>{t('svet.semantics')}</Checkbox>
				</Field>
			</Stack>

			<Stack gap={2}>
				<Text variant="caps">{t('svet.warnings')}</Text>
				{#each warnings as w (w.kind)}
					<Stack gap={1}>
						<Text variant="small" tone="warn">{t(`svet.warn.${w.kind}` as MessageKey, { n: w.regions.length })}</Text>
						<Cluster><Button variant="quiet" onclick={() => (shown = shown === w.kind ? null : w.kind)}>{shown === w.kind ? t('svet.warn.hide') : t('svet.warn.show')}</Button></Cluster>
					</Stack>
				{:else}
					<Text variant="why">{t('svet.warn.none')}</Text>
				{/each}
				<Text variant="why">{t('svet.warn.source')}</Text>
			</Stack>
		</Card>

		<Stage label={t('svet.map')}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('svet.map')}
				{summary}
				{fill}
				{edge}
				{highlight}
				selected={app.view.region}
				{labels}
				{markers}
				onpick={pick}
			/>
			{#snippet tl()}
				<Floating><Text variant="small">{t('svet.map_hint')} <Kbd>←</Kbd><Kbd>→</Kbd> <Kbd>Enter</Kbd></Text></Floating>
			{/snippet}
			{#snippet bl()}
				<Floating>
					<Legend items={legend}>{t('svet.legend_names', { n: cityCount })}</Legend>
				</Floating>
			{/snippet}
		</Stage>

		{#if region}
			{@const name = geo.name(region.id)}
			<Card label={name}>
				<Stack gap={1}>
					<Cluster justify="between" align="baseline">
						<Text variant="caps">{t('svet.region_caps', { id: region.id })}</Text>
						<Button variant="quiet" onclick={() => (app.view.region = null)}>{t('svet.clear')}</Button>
					</Cluster>
					<TextInput label={t('svet.edit.name', { name })} bind:value={nameDraft} onchange={rename} />
					{#if toponym}
						<Text>{t('svet.local_name')} <Ipa text={toponym.ipa} slashes /> <Text variant="why" as="span">{t('svet.local_name_meaning', { meaning: toponym.meaning })}</Text></Text>
					{/if}
				</Stack>
				<Field label={t('svet.language')}>
					<Segmented
						label={t('svet.edit.language', { name })}
						value={region.language ?? ''}
						options={world.languages.map((l) => ({ value: l.id, label: l.name ?? l.id }))}
						onchange={(v) => setRegion(region.id, 'language', t('svet.edit.language', { name }), v)}
					/>
				</Field>
				<Field label={t('svet.city')} hint={t('svet.city_note')}>
					<Segmented
						label={t('svet.edit.city', { name })}
						value={region.city ?? 0}
						options={cityOptions(region.city).map((n) => ({ value: n, label: n === 0 ? t('svet.city_none') : t('svet.city_size', { n }) }))}
						onchange={(v) => setRegion(region.id, 'city', t('svet.edit.city', { name }), v)}
					/>
				</Field>
				<Field label={t('svet.terrain')}>
					<Segmented
						label={t('svet.edit.terrain', { name })}
						value={region.terrain ?? 'plain'}
						options={terrains.map((x) => ({ value: x, label: t(`terrain.${x}` as MessageKey) }))}
						onchange={(v) => setRegion(region.id, 'terrain', t('svet.edit.terrain', { name }), v)}
					/>
				</Field>
				<Field label={t('svet.identity')} hint={t('svet.identity_note')}>
					<Segmented
						label={t('svet.edit.identity', { name })}
						value={region.identity ?? 'shared'}
						options={identities.map((x) => ({ value: x, label: t(`identity.${x}` as MessageKey) }))}
						onchange={(v) => setRegion(region.id, 'identity', t('svet.edit.identity', { name }), v)}
					/>
				</Field>
				<Field label={t('svet.settlement')} hint={t('svet.settlement_note')}>
					<Text variant="small">{t('svet.settlement_value', { villages: region.villages ?? 4, density: region.density ?? 1, prestige: (region.prestige as number | undefined) ?? 0.5 })}</Text>
				</Field>
				<Field label={t('svet.neighbours')}>
					<Cluster gap={1}>
						{#each region.neighbours ?? [] as n (n)}
							<Chip onclick={() => pick(n)}>{geo.name(n)}</Chip>
						{:else}
							<Text variant="why">{t('svet.neighbours_none')}</Text>
						{/each}
					</Cluster>
				</Field>
			</Card>
		{:else}
			<Card label={t('svet.empty_title')}>
				<Stack gap={1}>
					<Text variant="caps">{world.name ?? ''}</Text>
					<Text variant="h1">{t('svet.empty_title')}</Text>
					<Text variant="why">{t('svet.empty_hint')}</Text>
				</Stack>
			</Card>
		{/if}
	</Screen>
{/if}
