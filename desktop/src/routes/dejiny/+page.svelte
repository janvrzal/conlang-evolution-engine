<!-- Dějiny: mapa států v roce vybrané události, kronika zadání v pruzích a karta události (úpravy přes app.edit). -->
<script lang="ts">
	import {
		Button,
		Card,
		Checkbox,
		Chip,
		Cluster,
		EventLanes,
		Field,
		Floating,
		Legend,
		List,
		ListItem,
		Screen,
		Segmented,
		Select,
		Stack,
		Stage,
		Text,
		TextInput,
		WorldMap,
		formatYear,
		type EdgeStyle,
		type Lane,
		type LaneEvent,
		type LegendItem,
		type MapLabel
	} from '$lib/ds';
	import { number, t, type MessageKey } from '$lib/i18n.svelte';
	import {
		LANE_IDS,
		LANE_KINDS,
		arrowsOf,
		defaultEvent,
		fieldsOf,
		highlightOf,
		insertIndex,
		isStudyCase,
		languageShare,
		laneOf,
		outcomesOf,
		resolveRegion,
		snapYear,
		statesAt,
		type FieldSpec,
		type WorldEvent
	} from '$lib/model/dejiny';
	import { geography } from '$lib/model/geography';
	import { frameAt } from '$lib/model/languages';
	import { app } from '$lib/state.svelte';

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const events = $derived((world?.events ?? []) as WorldEvent[]);
	const startYear = $derived(world?.start_year ?? 0);
	const endYear = $derived(world?.end_year ?? 0);
	const regionIds = $derived(geo?.regions.map((r) => r.id) ?? []);

	const idx = $derived(app.view.event != null && app.view.event >= 0 && app.view.event < events.length ? app.view.event : null);
	const ev = $derived(idx != null ? events[idx] : null);
	/** rok mapy a kurzoru: rok vybrané události, jinak společný rok Výsledku */
	const year = $derived(ev ? ev.year : (app.view.year ?? endYear));

	// vybraná událost při prvním otevření: nejbližší společnému roku, jinak první elita
	let seeded = false;
	$effect(() => {
		if (seeded || !world) return;
		seeded = true;
		if (app.view.event != null || !events.length) return;
		const near = app.view.year != null ? events.map((e, i) => [i, Math.abs(e.year - app.view.year!)] as const).sort((a, b) => a[1] - b[1])[0]?.[0] : -1;
		const elite = events.findIndex((e) => e.kind === 'elite');
		app.view.event = near != null && near >= 0 ? near : elite >= 0 ? elite : 0;
	});

	// ---------- jména ----------
	const kindName = (kind: string) => {
		const key = `dejiny.kind.${kind}` as MessageKey;
		const own = t(key);
		return own !== key ? own : t(`kind.${kind}` as MessageKey);
	};
	const regionName = (id: unknown) => (typeof id === 'string' && geo ? geo.name(resolveRegion(id, regionIds) ?? id) : '—');
	const stateName = (id: unknown) => {
		const e = events.find((x) => (x.kind === 'state' || x.kind === 'secession') && x.id === id);
		return String(e?.name ?? app.frames.flatMap((f) => f.states).find((s) => s.id === id)?.name ?? id ?? '—');
	};
	const levelLabel = (prop: string, value: unknown) => {
		const key = `dejiny.lv.${prop}.${value}` as MessageKey;
		const text = t(key);
		return text !== key ? text : String(value ?? '—');
	};
	const regionsText = (list: unknown) => {
		const names = ((list as string[] | undefined) ?? []).map(regionName);
		return names.length > 2 ? `${names.slice(0, 2).join(', ')} +${names.length - 2}` : names.join(', ') || '—';
	};
	function titleOf(e: WorldEvent): string {
		const key = `dejiny.title.${e.kind}` as MessageKey;
		const params = {
			name: String(e.name ?? e.id ?? ''),
			state: stateName(e.state),
			of: STATE_OR_REGION(e.of),
			n: ((e.regions as unknown[] | undefined) ?? []).length,
			level: levelLabel(e.kind === 'border_policy' ? 'border' : 'policy', e.border ?? e.policy),
			from: regionName(e.from ?? e.source),
			to: regionName(e.to),
			seat: regionName(e.seat),
			regions: regionsText(e.regions),
			label: String(e.label ?? '')
		};
		const text = t(key, params);
		return text !== key ? text : kindName(e.kind);
	}
	const STATE_OR_REGION = (id: unknown) => (events.some((x) => (x.kind === 'state' || x.kind === 'secession') && x.id === id) ? stateName(id) : regionName(id));

	// ---------- mapa ----------
	const frame = $derived(app.frames.length ? frameAt(app.frames, year) : null);
	const statesNow = $derived(statesAt(events, year));
	const stateOf = $derived(new Map((frame?.states ?? []).flatMap((s, n) => s.regions.map((r) => [r, { ...s, n }] as const))));
	const policyOf = $derived(new Map((result?.states ?? []).map((s) => [s.id, s.policy])));
	const hit = $derived(ev ? highlightOf(ev, regionIds, statesNow) : []);
	const arrows = $derived(ev ? arrowsOf(ev, regionIds) : []);

	const regionFill = $derived((r: { id: string }) => {
		const s = stateOf.get(r.id);
		if (!s) return null;
		const policy = policyOf.get(s.id);
		return { color: 'ink', alpha: policy === 'enforced' ? 0.16 : policy === 'promoted' ? 0.08 : 0.04 };
	});
	const regionHatch = $derived((r: { id: string }) => {
		const s = stateOf.get(r.id);
		return s ? { angle: [0.6, -0.6, 1.4, 0.2][s.n % 4], color: 'muted', gap: 7, width: 0.6 } : null;
	});
	const edge = $derived((a: { region: string }, b: { region: string }): EdgeStyle | null => {
		if (a.region === b.region) return null;
		const sa = stateOf.get(a.region)?.id, sb = stateOf.get(b.region)?.id;
		if (sa !== sb) return { color: 'ink', width: 1.5, dash: 'state' };
		return { color: 'muted', width: 0.6, dash: 'dotted', alpha: 0.6 };
	});
	const labels = $derived.by(() => {
		if (!geo) return [];
		const out: MapLabel[] = (frame?.states ?? []).filter((s) => s.regions.length).map((s) => ({ text: s.name, region: s.regions[0], kind: 'state' as const, dy: 16 }));
		if (hit.length <= 4) for (const r of hit) out.push({ text: geo.name(r), region: r, kind: 'strong', dy: -12 });
		return out;
	});
	const summary = $derived(frame ? t('dejiny.map_summary', { states: frame.states.length, year: formatYear(year), n: hit.length }) : t('dejiny.map_summary_none', { n: hit.length }));
	const legend: LegendItem[] = $derived([
		...(frame ? [{ label: t('dejiny.legend.state_border'), kind: 'dashed' as const }] : []),
		{ label: t('dejiny.legend.hit'), kind: 'outline' as const, color: 'var(--red)' },
		...(arrows.length ? [{ label: t('dejiny.legend.arrow'), kind: 'line' as const, color: 'var(--red)' }] : [])
	]);

	// ---------- kronika ----------
	const lanes = $derived.by((): Lane[] => {
		const make = (id: string, kinds: string[]): Lane => ({
			id,
			label: t(`dejiny.lane.${id}` as MessageKey),
			events: events.flatMap((e, i): LaneEvent[] =>
				kinds.includes(e.kind)
					? [{ id: i, year: e.year, label: `${kindName(e.kind)} · ${titleOf(e)}`, state: i === idx ? 'selected' : isStudyCase(e) ? 'case' : undefined }]
					: []
			),
			empty: id === 'sounds' ? t('dejiny.lane.sounds_empty') : undefined
		});
		const bg = String(world?.background ?? 'none');
		return [
			...LANE_IDS.map((id) => make(id, LANE_KINDS[id])),
			{
				id: 'background',
				label: t('dejiny.lane.background'),
				muted: true,
				events: [],
				empty: bg === 'none' ? t('dejiny.lane.background_none') : t('dejiny.lane.background_on', { level: t(`dejiny.bg.${bg}` as MessageKey) })
			}
		];
	});

	function select(i: number | string) {
		const n = Number(i);
		app.view.event = n;
		app.view.year = events[n]?.year ?? app.view.year;
	}

	// ---------- úpravy ----------
	const schema = $derived(app.schema);
	const fields = $derived(ev ? fieldsOf(schema, ev.kind) : []);
	/** pole, která událost má; nepovinná nenastavená se nabízejí tlačítkem „+ pole“ */
	const shown = $derived(fields.filter((f) => f.required || ev?.[f.name] != null));
	const unset = $derived(fields.filter((f) => !f.required && ev?.[f.name] == null));
	function initial(f: FieldSpec): unknown {
		if (f.default != null) return f.default;
		if (f.kind === 'level') return f.levels?.[0];
		if (f.kind === 'regions') return [app.view.region ?? regionIds[0]];
		if (f.kind === 'language') return world?.languages[0]?.id;
		if (f.kind === 'bool') return false;
		if (f.kind === 'text') return '';
		return (f.max ?? 10) <= 1 ? 0.5 : 1;
	}
	const fieldLabel = (name: string) => t(`dejiny.f.${name}` as MessageKey);

	function setField(name: string, value: unknown) {
		if (idx == null || !ev) return;
		const i = idx;
		app.edit(t('dejiny.edited', { what: titleOf(ev), field: name === 'year' ? t('dejiny.year') : fieldLabel(name) }), (w) => {
			const e = w.events[i] as WorldEvent;
			if (value === undefined) delete e[name];
			else e[name] = value;
		});
	}
	function setYear(value: string | number) {
		if (value === '' || !world) return;
		const next = snapYear(Number(value), startYear, endYear);
		if (next === ev?.year) return;
		setField('year', next);
		app.view.year = next;
	}
	function setNumber(f: FieldSpec, value: string | number) {
		if (value === '') return f.required ? undefined : setField(f.name, undefined);
		setField(f.name, Number(value));
	}
	const listOf = (name: string) => ((ev?.[name] as string[] | undefined) ?? []);
	function toggleRegion(f: FieldSpec, region: string) {
		const list = listOf(f.name);
		if (list.includes(region)) {
			if (f.required && list.length <= 1) return;
			setField(f.name, list.filter((r) => r !== region));
		} else setField(f.name, [...list, region]);
	}
	function pick(region: string) {
		const f = fields.find((x) => x.kind === 'regions');
		if (f && ev) toggleRegion(f, region);
		else app.view.region = region;
	}
	let adding = $state('');
	let addingRegion = $state('');
	function add(kind: string) {
		adding = '';
		if (!kind || !world) return;
		const yearNew = snapYear(year, startYear, endYear);
		const ctx = {
			regions: [...(app.view.region ? [app.view.region] : []), ...regionIds.filter((r) => r !== app.view.region)],
			states: statesNow.map((s) => s.id),
			languages: world.languages.map((l) => l.id),
			label: t('dejiny.new_shift')
		};
		const made = defaultEvent(schema, kind, yearNew, ctx);
		const at = insertIndex(events, yearNew);
		app.edit(t('dejiny.added', { what: `${kindName(kind)} ${formatYear(yearNew)}` }), (w) => {
			w.events.splice(at, 0, made);
		});
		select(at);
	}
	function remove() {
		if (idx == null || !ev) return;
		const i = idx;
		app.edit(t('dejiny.deleted', { what: `${kindName(ev.kind)} ${formatYear(ev.year)}` }), (w) => {
			w.events.splice(i, 1);
		});
		app.view.event = null;
	}

	const addOptions = $derived([
		{ value: '', label: t('dejiny.add') },
		...LANE_IDS.flatMap((id) => (schema?.event_kinds ?? []).filter((k) => laneOf(k) === id).map((k) => ({ value: k, label: kindName(k) })))
	]);
	const stateOptions = $derived.by(() => {
		const list = new Map<string, string>();
		for (const e of events) if ((e.kind === 'state' || e.kind === 'secession') && typeof e.id === 'string') list.set(e.id, stateName(e.id));
		return list;
	});
	const optionsFor = (current: unknown, base: [string, string][]) => {
		const out = base.map(([value, label]) => ({ value, label }));
		if (typeof current === 'string' && current && !out.some((o) => o.value === current)) out.push({ value: current, label: regionName(current) });
		return out;
	};
	const stateChoices = (current: unknown) => optionsFor(current, [...stateOptions.entries()]).map((o) => (stateOptions.has(o.value) ? o : { ...o, label: String(o.value) }));
	const regionChoices = (current: unknown) => optionsFor(current, regionIds.map((r) => [r, geo?.name(r) ?? r]));
	const languageChoices = (f: FieldSpec) => [...(f.required ? [] : [{ value: '', label: t('dejiny.language_auto') }]), ...(world?.languages ?? []).map((l) => ({ value: l.id, label: l.name ?? l.id }))];
	const stepOf = (f: FieldSpec) => (f.kind === 'integer' ? 1 : (f.max ?? 10) <= 1 ? 0.05 : 0.1);

	// ---------- co z události v běhu vzešlo ----------
	const outcomes = $derived.by(() => {
		if (!ev) return null;
		if (!result) return { note: t(app.running ? 'dejiny.outcomes_running' : 'dejiny.outcomes_no_run'), items: [] };
		if (ev.year > result.year) return { note: t('dejiny.outcomes_late'), items: [] };
		const items: { text: string; href: string; meta: string }[] = outcomesOf(ev, result.events, regionIds).map((o) => ({
			text: `${formatYear(o.year)} · ${t(`dejiny.out.${o.kind}` as MessageKey, { name: o.name ?? '', n: number(o.n ?? 0) })}`,
			href: `/kronika?year=${o.year}`,
			meta: t('dejiny.out.link.kronika')
		}));
		if (ev.kind === 'elite' && geo) {
			const seat = resolveRegion(ev.seat, regionIds);
			const code = (ev.language as string | undefined) ?? world?.regions.find((r) => r.id === resolveRegion(ev.from, regionIds))?.language;
			const share = seat && code ? languageShare(result, seat, code, (village) => geo.regionOf.get(village)) : null;
			if (share && seat && code)
				items.push({
					text: t('dejiny.out.lang_share', { region: geo.name(seat), year: formatYear(result.year), total: share.total, words: share.words, language: world?.languages.find((l) => l.id === code)?.name ?? code }),
					href: `/slova?region=${seat}`,
					meta: t('dejiny.out.link.slova')
				});
		}
		return { note: app.stale ? t('dejiny.outcomes_stale') : items.length ? '' : t('dejiny.outcomes_none'), items };
	});
</script>

{#if !world || !geo}
	<Screen><Text variant="why">{t('dejiny.empty')}</Text></Screen>
{:else}
	<Screen columns={['fill', 360]} rows={['fill', 'auto']} label={t('dejiny.title')}>
		<Stage label={t('dejiny.map', { year: formatYear(year) })}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('dejiny.map', { year: formatYear(year) })}
				{summary}
				regionFill={frame ? regionFill : undefined}
				regionHatch={frame ? regionHatch : undefined}
				{edge}
				highlight={hit}
				selected={app.view.region}
				{labels}
				{arrows}
				onpick={pick}
			/>
			{#snippet tl()}
				<Floating>
					<Stack gap={1}>
						<Text variant="big" num>{formatYear(year)}</Text>
						<Text variant="why">
							{frame ? t('dejiny.states', { n: frame.states.length }) : t('dejiny.states_none')}{frame && frame.year !== year ? ` · ${t('dejiny.frame_note', { year: formatYear(frame.year) })}` : ''}
						</Text>
					</Stack>
				</Floating>
			{/snippet}
			{#snippet tr()}
				<Floating><Text variant="small">{t('dejiny.keys')}</Text></Floating>
			{/snippet}
			{#snippet bl()}
				<Floating><Legend items={legend} /></Floating>
			{/snippet}
		</Stage>

		<Card label={ev ? titleOf(ev) : t('dejiny.title')} rowSpan={2}>
			{#if ev && idx != null}
				<Stack gap={1}>
					<Text variant="caps">{t(`dejiny.lane.${laneOf(ev.kind)}` as MessageKey)} · {kindName(ev.kind)}{isStudyCase(ev) ? ` · ${t('dejiny.kind_case')}` : ''}</Text>
					<Text variant="h1">{titleOf(ev)}</Text>
				</Stack>
				<Stack gap={0}>
					<Field label={t('dejiny.year')} for="dejiny-year" hint={t('dejiny.year_hint')}>
						<TextInput id="dejiny-year" type="number" width="s" step={25} min={startYear} max={endYear} value={ev.year} onchange={setYear} />
					</Field>
					{#each shown as f (f.name)}
						{@const value = ev[f.name]}
						<Field label={fieldLabel(f.name)} for={f.kind === 'regions' || f.kind === 'level' || f.kind === 'bool' ? undefined : `dejiny-f-${f.name}`}>
							{#if f.kind === 'level' && f.levels}
								<Segmented label={fieldLabel(f.name)} value={String(value ?? f.levels[0])} options={f.levels.map((l) => ({ value: l, label: levelLabel(f.name, l) }))} onchange={(v) => setField(f.name, v)} />
							{:else if f.kind === 'state'}
								<Select id={`dejiny-f-${f.name}`} label={fieldLabel(f.name)} value={String(value ?? '')} options={stateChoices(value)} onchange={(v) => setField(f.name, v)} />
							{:else if f.kind === 'region'}
								<Select id={`dejiny-f-${f.name}`} label={fieldLabel(f.name)} value={String(value ?? '')} options={regionChoices(value)} onchange={(v) => setField(f.name, v)} />
							{:else if f.kind === 'language'}
								<Select id={`dejiny-f-${f.name}`} label={fieldLabel(f.name)} value={String(value ?? '')} options={languageChoices(f)} onchange={(v) => setField(f.name, v === '' ? undefined : v)} />
							{:else if f.kind === 'regions'}
								<Cluster gap={1}>
									{#each listOf(f.name) as r (r)}
										<Chip state="on" onclick={() => toggleRegion(f, r)} title={t('dejiny.regions_remove', { name: regionName(r) })}>{regionName(r)} ×</Chip>
									{/each}
								</Cluster>
								<Select
									label={t('dejiny.regions_add')}
									bind:value={addingRegion}
									options={[{ value: '', label: t('dejiny.regions_add') }, ...regionChoices('').filter((o) => !listOf(f.name).includes(o.value))]}
									onchange={(v) => {
										addingRegion = '';
										if (v) toggleRegion(f, v);
									}}
								/>
							{:else if f.kind === 'bool'}
								<Checkbox checked={value === true} onchange={(c) => setField(f.name, c)}>{value === true ? t('dejiny.yes') : t('dejiny.no')}</Checkbox>
							{:else if f.kind === 'number' || f.kind === 'integer'}
								<TextInput id={`dejiny-f-${f.name}`} type="number" width="s" step={stepOf(f)} min={f.min} max={f.max} value={typeof value === 'number' ? value : ''} onchange={(v) => setNumber(f, v)} />
							{:else}
								<TextInput id={`dejiny-f-${f.name}`} value={String(value ?? '')} onchange={(v) => setField(f.name, v === '' && !f.required ? undefined : String(v))} />
							{/if}
						</Field>
					{/each}
				</Stack>
				{#if unset.length}
					<Cluster gap={1}>
						{#each unset as f (f.name)}<Button variant="quiet" onclick={() => setField(f.name, initial(f))}>+ {fieldLabel(f.name)}</Button>{/each}
					</Cluster>
				{/if}
				<Text variant="why">{t(`dejiny.hint.${ev.kind}` as MessageKey)}</Text>
				<Stack gap={1}>
					<Text variant="caps">{t('dejiny.outcomes')}</Text>
					{#if outcomes?.items.length}
						<List label={t('dejiny.outcomes')}>
							{#each outcomes.items as item (item.text)}<ListItem href={item.href} meta={item.meta}>{item.text}</ListItem>{/each}
						</List>
					{/if}
					{#if outcomes?.note}<Text variant="why">{outcomes.note}</Text>{/if}
				</Stack>
				<Cluster><Button variant="quiet" onclick={remove}>{t('dejiny.delete')}</Button></Cluster>
			{:else}
				<Text variant="why">{t('dejiny.select_hint')}</Text>
			{/if}
		</Card>

		<Stack gap={1} label={t('dejiny.lanes')}>
			<Cluster gap={3}>
				<Text variant="caps">{t('dejiny.chronicle', { n: events.length })}</Text>
				{#if schema}
					<Select id="dejiny-add" label={t('dejiny.add_label')} bind:value={adding} options={addOptions} onchange={add} />
				{:else}
					<Button disabled title={t('dejiny.add_need_engine')}>{t('dejiny.add')}</Button>
				{/if}
				<Text variant="why">{t('dejiny.chronicle_hint')}</Text>
			</Cluster>
			<EventLanes start={startYear} end={endYear} {lanes} cursor={year} label={t('dejiny.lanes')} onselect={(e) => select(e.id)} />
		</Stack>
	</Screen>
{/if}
