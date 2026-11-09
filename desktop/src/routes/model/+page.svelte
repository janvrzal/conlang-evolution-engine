<!-- Model: parametry enginu podle rolí. World = slovní úrovně (tabulky), active = páky pod „Pro pokročilé“,
     fixed = skryté konstanty (jen počet, přepisy světa a výpis ke čtení). Hodnoty světa jsou v world.parameters. -->
<script lang="ts">
	import { Area, Banner, Button, Card, Cluster, Floating, Ledger, LedgerRow, List, ListItem, Range, Screen, Segmented, Stack, Table, Td, Text, TextInput, Tr } from '$lib/ds';
	import { i18n, t, type MessageKey } from '$lib/i18n.svelte';
	import {
		changedIn,
		fmt,
		isChanged,
		isLevelTable,
		lead,
		roundTo,
		same,
		stepFor,
		tableView,
		unknownKeys,
		valueOf,
		withCell,
		type ParamItem
	} from '$lib/model/model';
	import { app } from '$lib/state.svelte';

	const schema = $derived(app.schema);
	const world = $derived(app.world);
	const locale = $derived(i18n.locale as 'cs' | 'en');
	const roles = $derived(schema?.parameters_by_role ?? null);
	const overrides = $derived(world?.parameters as Record<string, unknown> | undefined);

	const worldItems = $derived(roles?.world.items ?? []);
	const activeItems = $derived(roles?.active.items ?? []);
	const fixedItems = $derived(roles?.fixed.items ?? []);
	const groups = $derived(roles?.active.groups ?? []);

	let group = $state('');
	let picked = $state('');
	let fullShown = $state<Record<string, boolean>>({});
	let showFixed = $state(false);
	let draft = $state<Record<string, number>>({});
	const timers: Record<string, ReturnType<typeof setTimeout>> = {};

	// bez výběru: skupina s první změněnou pákou, jinak první neprázdná
	const activeGroup = $derived(
		groups.some((g) => g.id === group)
			? group
			: (changedIn(activeItems, overrides)[0]?.group ?? groups.find((g) => activeItems.some((i) => i.group === g.id))?.id ?? '')
	);
	const shownActive = $derived(activeItems.filter((i) => i.group === activeGroup));
	const selected = $derived(worldItems.find((i) => i.name === picked) ?? changedIn(worldItems, overrides)[0] ?? worldItems.find((i) => i.name === 'policy_levels') ?? worldItems[0]);
	const changedWorld = $derived(changedIn(worldItems, overrides));
	const changedActive = $derived(changedIn(activeItems, overrides));
	const changedFixed = $derived(changedIn(fixedItems, overrides));
	const changedAll = $derived(changedWorld.length + changedActive.length + changedFixed.length);
	const unknown = $derived(unknownKeys([worldItems, activeItems, fixedItems], overrides));

	// název z katalogu textů, jinak kód parametru
	function msg(prefix: string, key: string, fallback: string): string {
		const k = `${prefix}${key}` as MessageKey;
		const text = t(k);
		return text === k ? fallback : text;
	}
	const titleOf = (i: ParamItem) => msg('model.p.', i.name, i.title ?? i.name);
	const kindOf = (k: string) => msg('model.k.', k, k);

	function show(v: unknown): string {
		if (typeof v === 'number') return fmt(v, locale);
		if (v && typeof v === 'object') {
			const view = tableView(v);
			if (!view) return '{}';
			return view.rows
				.map((r) => `${r.key}: ${r.cells.length === 1 && view.head[0] === '' ? fmt(r.cells[0], locale) : r.cells.map((c) => fmt(c, locale)).join('/')}`)
				.join(', ');
		}
		return String(v ?? '—');
	}

	// zápis do světa přes app.edit; hodnota rovná výchozí přepis odstraní
	function write(item: ParamItem, next: unknown) {
		app.edit(t('model.edit_one', { name: titleOf(item) }), (w) => {
			const params = { ...(w.parameters ?? {}) } as Record<string, unknown>;
			if (same(next, item.default)) delete params[item.name];
			else params[item.name] = next;
			w.parameters = params as Record<string, number>;
		});
	}
	function reset(items: ParamItem[], label?: string) {
		app.edit(label ?? t('model.edit_reset', { name: titleOf(items[0]) }), (w) => {
			const params = { ...(w.parameters ?? {}) } as Record<string, unknown>;
			for (const i of items) delete params[i.name];
			w.parameters = params as Record<string, number>;
		});
		for (const i of items) delete draft[i.name];
	}
	function slide(item: ParamItem, v: number) {
		draft[item.name] = v;
		clearTimeout(timers[item.name]);
		timers[item.name] = setTimeout(() => {
			write(item, v);
			delete draft[item.name];
		}, 350);
	}
	function typed(item: ParamItem, raw: string | number) {
		const n = Number(raw);
		if (raw === '' || !Number.isFinite(n)) return;
		write(item, n);
	}
	function cell(item: ParamItem, path: string[], raw: string | number) {
		const n = Number(raw);
		if (raw === '' || !Number.isFinite(n)) return;
		write(item, withCell(valueOf(item, overrides), path, n));
	}
	const num = (v: unknown) => (typeof v === 'number' ? v : 0);
	const range = (i: ParamItem) => (typeof i.min === 'number' && typeof i.max === 'number' ? { min: i.min, max: i.max } : null);
</script>

{#if !schema}
	<Screen label={t('model.title')}>
		<Stack gap={3}>
			<Text variant="h1">{t('model.offline_title')}</Text>
			<Text variant="why">{t('model.offline')}</Text>
		</Stack>
	</Screen>
{:else if !world}
	<Screen label={t('model.title')}>
		<Stack gap={3}>
			<Text variant="h1">{t('model.title')}</Text>
			<Text variant="why">{t('model.no_world')}</Text>
		</Stack>
	</Screen>
{:else}
	<Screen columns={[320, 'fill', 320]} label={t('model.title')}>
		<Area label={t('model.world_title')} scroll>
			<Card label={t('model.world_title')}>
				<Stack gap={3}>
					<Stack gap={1}>
						<Text variant="caps">{t('model.world_caps', { n: worldItems.length })}</Text>
						<Text variant="h2">{t('model.world_title')}</Text>
						<Text variant="why">{t('model.world_why')}</Text>
					</Stack>
					<List label={t('model.world_list')}>
						{#each worldItems as item (item.name)}
							{@const n = changedIn([item], overrides).length}
							<ListItem current={item.name === selected?.name} onclick={() => (picked = item.name)} meta={n ? t('model.changed') : tableView(item.default) ? t('model.n_levels', { n: tableView(item.default)?.rows.length ?? 0 }) : ''}>{titleOf(item)}</ListItem>
						{/each}
					</List>
					{#if selected}
						{@const cur = valueOf(selected, overrides)}
						{@const def = tableView(selected.default)}
						{@const view = tableView(cur) ?? def}
						<Stack gap={2}>
							<Text variant="caps">{titleOf(selected)}</Text>
							<Text variant="small" tone="muted">{selected.name}</Text>
							<Text variant="why">{lead(selected.description as string).short}</Text>
							{#if view && isLevelTable(selected)}
								{@const two = view.head[0] !== ''}
								<Table head={[{ label: t('model.levels') }, ...(two ? view.head.map((h) => ({ label: kindOf(h), num: true })) : [{ label: t('model.col_world'), num: true }])]}>
									{#each view.rows as row (row.key)}
										<Tr>
											<Td>{kindOf(row.key)}</Td>
											{#each row.cells as c, ci (ci)}
												{@const path = two ? [row.key, view.head[ci]] : [row.key]}
												{@const d = two ? (def?.rows.find((r) => r.key === row.key)?.cells[ci] as number) : (def?.rows.find((r) => r.key === row.key)?.cells[0] as number)}
												<Td num>
													<Stack gap={0} align="end">
														<TextInput
															type="number"
															width="s"
															step={0.05}
															value={num(c)}
															label={t('model.cell', { row: kindOf(row.key), col: two ? kindOf(view.head[ci]) : titleOf(selected) })}
															onchange={(v) => cell(selected, path, v)}
														/>
														<Text variant="small" tone={same(c, d) ? 'muted' : 'red'}>{t('model.default_value', { value: fmt(d, locale) })}</Text>
													</Stack>
												</Td>
											{/each}
										</Tr>
									{/each}
								</Table>
							{:else if view}
								<Table head={[{ label: t('model.levels') }, ...view.head.map((h) => ({ label: kindOf(h), num: true }))]}>
									{#each view.rows as row (row.key)}
										<Tr>
											<Td>{kindOf(row.key)}</Td>
											{#each row.cells as c, ci (ci)}<Td num>{show(c)}</Td>{/each}
										</Tr>
									{/each}
								</Table>
								<Text variant="why">{t('model.table_readonly')}</Text>
							{:else}
								<Text variant="why">{t('model.empty_table')}</Text>
							{/if}
							{#if isChanged(selected, overrides)}
								<Cluster><Button variant="quiet" onclick={() => reset([selected])}>{t('model.reset')}</Button></Cluster>
							{/if}
						</Stack>
					{/if}
				</Stack>
			</Card>
		</Area>

		<Area label={t('model.active_title')} scroll>
			<Stack gap={3}>
				<Stack gap={1}>
					<Cluster gap={3} align="baseline">
						<Stack gap={0}>
							<Text variant="caps">{t('model.active_caps', { n: activeItems.length })}</Text>
							<Text variant="h1">{t('model.active_title')}</Text>
						</Stack>
						<Segmented
							label={t('model.group')}
							options={groups.filter((g) => activeItems.some((i) => i.group === g.id)).map((g) => ({ value: g.id, label: msg('model.g.', g.id, g.title) }))}
							value={activeGroup}
							onchange={(v) => (group = v)}
						/>
					</Cluster>
					<Text variant="why">{t('model.active_why')}</Text>
				</Stack>
				{#if changedAll}
					<Banner>
						{t('model.changed_banner', { n: changedAll })}
						{#snippet actions()}
							<Button variant="quiet" onclick={() => reset([...changedWorld, ...changedActive, ...changedFixed], t('model.edit_reset_all'))}>{t('model.reset_all')}</Button>
						{/snippet}
					</Banner>
				{/if}
				{#each shownActive as item (item.name)}
					{@const cur = draft[item.name] ?? valueOf(item, overrides)}
					{@const changed = isChanged(item, overrides) || (item.name in draft && !same(draft[item.name], item.default))}
					{@const r = item.kind === 'number' ? range(item) : null}
					{@const d = lead(item.description as string)}
					<Stack gap={1}>
						<Cluster justify="between" align="baseline" wrap={false}>
							<Cluster gap={2} align="baseline">
								<Text variant="strong">{titleOf(item)}</Text>
								<Text variant="small" tone="muted">{item.name}</Text>
							</Cluster>
							{#if item.kind === 'number'}
								<Text variant="strong" num tone={changed ? 'red' : undefined}>{fmt(cur, locale)}</Text>
							{/if}
						</Cluster>
						<Text variant="why">{fullShown[item.name] ? (item.description as string).replace(/``/g, '') : d.short}</Text>
						{#if d.cut}
							<Cluster><Button variant="quiet" onclick={() => (fullShown[item.name] = !fullShown[item.name])}>{fullShown[item.name] ? t('model.less') : t('model.full')}</Button></Cluster>
						{/if}
						{#if r}
							{@const step = stepFor(r.min, r.max)}
							<Range label={titleOf(item)} min={r.min} max={r.max} {step} value={num(cur)} oninput={(v) => slide(item, roundTo(v, step))} />
						{:else if item.kind === 'number'}
							<Cluster><TextInput type="number" width="s" step={0.05} value={num(cur)} label={titleOf(item)} onchange={(v) => typed(item, v)} /></Cluster>
						{:else}
							{@const view = tableView(cur)}
							{#if view}
								<Table head={[{ label: '' }, ...view.head.map((h) => ({ label: kindOf(h), num: true }))]}>
									{#each view.rows as row (row.key)}
										<Tr><Td>{kindOf(row.key)}</Td>{#each row.cells as c, ci (ci)}<Td num>{show(c)}</Td>{/each}</Tr>
									{/each}
								</Table>
							{:else}
								<Text variant="small" tone="muted">{t('model.empty_table')}</Text>
							{/if}
						{/if}
						<Cluster gap={2}>
							<Text variant="small" tone={changed ? 'red' : 'muted'}>{changed ? t('model.default_value', { value: show(item.default) }) : t('model.unchanged')}</Text>
							{#if changed}<Button variant="quiet" onclick={() => reset([item])}>{t('model.reset')}</Button>{/if}
						</Cluster>
					</Stack>
				{:else}
					<Text variant="why">{t('model.no_items')}</Text>
				{/each}
				<Text variant="small" tone="muted">{t('model.desc_note')}</Text>
			</Stack>
		</Area>

		<Area label={t('model.fixed_title')} as="aside" scroll>
			<Card label={t('model.fixed_title')}>
				<Stack gap={3}>
					<Stack gap={1}>
						<Text variant="caps">{t('model.fixed_caps', { n: fixedItems.length })}</Text>
						<Text variant="h2">{t('model.fixed_title')}</Text>
						<Text variant="why">{t('model.fixed_why')}</Text>
					</Stack>
					{#if changedFixed.length}
						<Floating>
							<Stack gap={2}>
								<Text variant="caps" tone="red">{t('model.fixed_over', { n: changedFixed.length })}</Text>
								<Ledger termWidth={150}>
									{#each changedFixed as item (item.name)}
										<LedgerRow term={item.name}>
											<Text as="span" num>{show(valueOf(item, overrides))}</Text> <Text as="span" variant="why">{t('model.default_value', { value: show(item.default) })}</Text>
										</LedgerRow>
									{/each}
								</Ledger>
								<Cluster><Button variant="quiet" onclick={() => reset(changedFixed)}>{t('model.reset')}</Button></Cluster>
							</Stack>
						</Floating>
					{:else}
						<Text variant="why">{t('model.fixed_none')}</Text>
					{/if}
					<Cluster>
						<Button pressed={showFixed} onclick={() => (showFixed = !showFixed)}>{showFixed ? t('model.hide_all') : t('model.show_all_n', { n: fixedItems.length })}</Button>
					</Cluster>
					{#if showFixed}
						<Table caption={t('model.fixed_list')} head={[{ label: '' }, { label: t('model.col_default'), num: true }]}>
							{#each fixedItems as item (item.name)}
								<Tr><Td>{item.name}</Td><Td num tone={isChanged(item, overrides) ? 'red' : undefined}>{show(valueOf(item, overrides))}</Td></Tr>
							{/each}
						</Table>
					{/if}
					<Text variant="why">{t('model.fixed_twin')}</Text>
					{#if unknown.length}
						<Stack gap={1}>
							<Text variant="caps">{t('model.unknown_title')}</Text>
							<Text variant="why">{t('model.unknown_why')}</Text>
							<Text variant="small">{unknown.join(', ')}</Text>
						</Stack>
					{/if}
				</Stack>
			</Card>
		</Area>
	</Screen>
{/if}
