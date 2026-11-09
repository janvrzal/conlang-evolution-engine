<!-- Svět: nastavení světa, mapa krajů (jazyk na počátku) s nástroji (výběr, nový kraj, posun,
     sousedé) a karta vybraného kraje s úpravou. Úpravy jdou přes app.edit (Zpět/Znovu, Vrátit). -->
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
		Select,
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
		type MapEdit,
		type MapMarker,
		type MapVillage
	} from '$lib/ds';
	import { t, type MessageKey } from '$lib/i18n.svelte';
	import { geography } from '$lib/model/geography';
	import { addRegion, cityOptions, eventsUsingRegion, hasCity, levelsInOrder, regionsPerLanguage, removeRegion, toggleNeighbours, worldWarnings } from '$lib/model/svet';
	import { app } from '$lib/state.svelte';

	const world = $derived(app.world);
	// vsi z běhu jen dokud zadání odpovídá běhu; po úpravě krajů se mapa kreslí ze zadání
	const geo = $derived(world ? geography(world, app.stale ? null : app.result) : null);
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

	// ---- nástroje mapy (V výběr, R nový kraj, M posun, S sousedé)
	type Tool = MapEdit['mode'];
	let tool = $state<Tool>('select');
	const TOOLS: { value: Tool; key: string }[] = [
		{ value: 'select', key: 'v' },
		{ value: 'add', key: 'r' },
		{ value: 'move', key: 'm' },
		{ value: 'link', key: 's' }
	];
	const edit: MapEdit = $derived({
		mode: tool,
		onadd: (x, y) => {
			let id = '';
			app.edit(t('svet.edit.add'), (w) => (id = addRegion(w, x, y, t('svet.new_region'))));
			app.view.region = id;
		},
		onmove: (id, x, y) =>
			app.edit(t('svet.edit.move', { name: geo?.name(id) ?? id }), (w) => {
				const r = w.regions.find((q) => q.id === id);
				if (r) r.position = [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
			}),
		onlink: (a, b) => {
			const names = { a: geo?.name(a) ?? a, b: geo?.name(b) ?? b };
			app.edit(t('svet.edit.link', names), (w) => toggleNeighbours(w, a, b));
			app.view.region = a;
		}
	});
	function toolKey(event: KeyboardEvent) {
		const target = event.target as HTMLElement;
		if (event.metaKey || event.ctrlKey || event.altKey || target.closest('input, textarea, select')) return;
		const found = TOOLS.find((x) => x.key === event.key.toLowerCase());
		if (found) tool = found.value;
		else if (event.key === 'Escape') tool = 'select';
	}

	// ---- osídlení, poloha, sousedé, smazání
	const setNumber = (id: string, key: 'villages' | 'density' | 'prestige', label: string, raw: string | number, ok: (n: number) => boolean) => {
		const n = Number(raw);
		if (String(raw).trim() === '' || !Number.isFinite(n) || !ok(n)) return false;
		app.edit(label, (w) => {
			const r = w.regions.find((x) => x.id === id);
			if (r) (r as Record<string, unknown>)[key] = n;
		});
		return true;
	};
	let villages = $state<string | number>(4), density = $state<string | number>(1), prestige = $state<string | number>(0.5);
	let posX = $state<string | number>(0), posY = $state<string | number>(0);
	let numberError = $state<string | null>(null);
	$effect(() => {
		if (!region) return;
		villages = region.villages ?? 4;
		density = region.density ?? 1;
		prestige = (region.prestige as number | undefined) ?? 0.5;
		posX = region.position[0];
		posY = region.position[1];
		numberError = null;
	});
	const commit = (key: 'villages' | 'density' | 'prestige', raw: string | number) => {
		if (!region) return;
		const name = geo?.name(region.id) ?? region.id;
		const rules = { villages: (n: number) => Number.isInteger(n) && n >= 1 && n <= 12, density: (n: number) => n > 0 && n <= 100, prestige: (n: number) => n >= 0 };
		numberError = setNumber(region.id, key, t(`svet.edit.${key}` as MessageKey, { name }), raw, rules[key]) ? null : t(`svet.bad.${key}` as MessageKey);
	};
	const commitPosition = () => {
		if (!region) return;
		const x = Number(posX), y = Number(posY), id = region.id;
		if (!Number.isFinite(x) || !Number.isFinite(y) || (x === region.position[0] && y === region.position[1])) return;
		app.edit(t('svet.edit.move', { name: geo?.name(id) ?? id }), (w) => {
			const r = w.regions.find((q) => q.id === id);
			if (r) r.position = [x, y];
		});
	};
	const linkOptions = $derived(
		region && world && geo
			? [{ value: '', label: t('svet.neighbour_add') }, ...world.regions.filter((r) => r.id !== region.id && !(region.neighbours ?? []).includes(r.id)).map((r) => ({ value: r.id, label: geo.name(r.id) }))]
			: []
	);
	const link = (a: string, b: string) => {
		if (!b) return;
		app.edit(t('svet.edit.link', { a: geo?.name(a) ?? a, b: geo?.name(b) ?? b }), (w) => toggleNeighbours(w, a, b));
	};
	const remove = (id: string) => {
		const name = geo?.name(id) ?? id;
		app.edit(t('svet.edit.remove', { name }), (w) => removeRegion(w, id));
		app.view.region = null;
	};
</script>

<svelte:window onkeydown={toolKey} />

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
				{edit}
				onpick={pick}
			/>
			{#snippet tl()}
				<Floating tight>
					<Segmented
						label={t('svet.tools')}
						bind:value={tool}
						options={TOOLS.map((x) => ({ value: x.value, label: `${t(`svet.tool.${x.value}` as MessageKey)} (${x.key.toUpperCase()})` }))}
					/>
				</Floating>
				<Floating><Text variant="small">{t(`svet.tool_hint.${tool}` as MessageKey)}{#if tool === 'select'} <Kbd>←</Kbd><Kbd>→</Kbd> <Kbd>Enter</Kbd>{/if}</Text></Floating>
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
				<Field label={t('svet.settlement')} hint={t('svet.settlement_note')} error={numberError}>
					<Cluster gap={2} align="end">
						<Stack gap={0}><Text variant="small">{t('svet.villages')}</Text><TextInput type="number" width="s" min={1} max={12} step={1} label={t('svet.villages')} bind:value={villages} onchange={(v) => commit('villages', v)} /></Stack>
						<Stack gap={0}><Text variant="small">{t('svet.density')}</Text><TextInput type="number" width="s" min={0.1} max={100} step={0.1} label={t('svet.density')} bind:value={density} onchange={(v) => commit('density', v)} /></Stack>
						<Stack gap={0}><Text variant="small">{t('svet.prestige')}</Text><TextInput type="number" width="s" min={0} step={0.1} label={t('svet.prestige')} bind:value={prestige} onchange={(v) => commit('prestige', v)} /></Stack>
					</Cluster>
				</Field>
				<Field label={t('svet.position')} hint={t('svet.position_note')}>
					<Cluster gap={2}>
						<TextInput type="number" width="s" step={0.5} label={t('svet.position_x')} bind:value={posX} onchange={commitPosition} />
						<TextInput type="number" width="s" step={0.5} label={t('svet.position_y')} bind:value={posY} onchange={commitPosition} />
						<Text as="span" tone="muted">km</Text>
					</Cluster>
				</Field>
				<Field label={t('svet.neighbours')} hint={t('svet.neighbours_note')}>
					<Cluster gap={1}>
						{#each region.neighbours ?? [] as n (n)}
							<Chip onclick={() => pick(n)} onremove={() => link(region.id, n)} removeLabel={t('svet.neighbour_remove', { name: geo.name(n) })}>{geo.name(n)}</Chip>
						{:else}
							<Text variant="why">{t('svet.neighbours_none')}</Text>
						{/each}
					</Cluster>
					<Select label={t('svet.neighbour_add')} value="" options={linkOptions} onchange={(v) => link(region.id, v)} />
				</Field>
				<Stack gap={1}>
					<Cluster><Button variant="quiet" onclick={() => remove(region.id)}>{t('svet.remove')}</Button></Cluster>
					{#if eventsUsingRegion(world, region.id)}<Text variant="why">{t('svet.remove_note', { n: eventsUsingRegion(world, region.id) })}</Text>{/if}
				</Stack>
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
