<!-- Pojmy (slovník světa): velikost slovníku, základní pojmy s doménami a hledáním,
     vlastní pojmy zadání (přidat, upravit, smazat přes app.edit). Obrazovka Zadání bez běhu funguje. -->
<script lang="ts">
	import {
		Area,
		Button,
		Cluster,
		Field,
		Ledger,
		LedgerRow,
		List,
		ListItem,
		Screen,
		Select,
		Stack,
		Table,
		Td,
		Text,
		TextInput,
		Tr
	} from '$lib/ds';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import {
		BASE_CONCEPTS,
		BASE_SIZE,
		DOMAINS,
		RELATION_KINDS,
		WORD_CLASSES,
		checkDraft,
		conceptOf,
		customConcepts,
		draftOf,
		emptyDraft,
		filterConcepts,
		isInvented,
		sizeFactor,
		sizeOf,
		sizeOptions,
		type CustomConcept,
		type Domain,
		type Draft
	} from '$lib/model/pojmy';
	import { app } from '$lib/state.svelte';

	const SIZE_TEXT: Record<number, MessageKey> = {
		[BASE_SIZE]: 'pojmy.size.base',
		200: 'pojmy.size.more',
		500: 'pojmy.size.500',
		1000: 'pojmy.size.1000'
	};

	const world = $derived(app.world);
	const current = $derived(sizeOf(world));
	const vocabulary = $derived(app.schema?.vocabulary);
	const sizes = $derived(vocabulary ? sizeOptions(vocabulary) : []);
	const custom = $derived(customConcepts(world));

	const baseLabel = (id: string) => conceptLabel(id, i18n.locale);
	const domainLabel = (d: Domain | undefined) => (d ? t(`pojmy.domain.${d}` as MessageKey) : t('pojmy.domain.default'));
	const customName = (c: CustomConcept) => c.gloss ?? c.id;
	const customMeta = (c: CustomConcept) =>
		isInvented(c) ? t('pojmy.invented') : c.wold ? t('pojmy.custom.wold', { id: c.wold }) : t('pojmy.custom.concepticon', { id: String(c.concepticon) });

	// volby velikosti: co přidají a kolikrát déle běží oproti základnímu slovníku
	const sizeText = (n: number) => t(SIZE_TEXT[n] ?? (n === vocabulary?.max ? 'pojmy.size.max' : 'pojmy.size.other'));
	const runText = (n: number) =>
		n === BASE_SIZE
			? t('pojmy.run.base')
			: t('pojmy.run.factor', { x: sizeFactor(n, BASE_SIZE).toLocaleString(i18n.locale === 'cs' ? 'cs-CZ' : 'en-GB', { maximumFractionDigits: 1 }) });

	function choose(n: number) {
		if (!world || n === current) return;
		app.edit(t('pojmy.edit.size', { n: number(n) }), (w) => {
			w.vocabulary = n;
		});
	}

	// základní pojmy: hledání v id i v popisku
	let query = $state('');
	const baseRows = $derived(filterConcepts(BASE_CONCEPTS, query, (c) => baseLabel(c.id)));

	// vlastní pojmy: formulář je buď nový pojem, nebo úprava pojmu s daným id (hledá se při zápisu)
	let editingId = $state<string | null>(null);
	let draft = $state<Draft>(emptyDraft());
	// prázdné ID se hlásí až po prvním psaní, ne hned u prázdného formuláře
	let typed = $state(false);
	const taken = $derived(
		new Set([...BASE_CONCEPTS.map((c) => c.id), ...custom.filter((c) => c.id !== editingId).map((c) => c.id)])
	);
	const problems = $derived(checkDraft(draft, taken));
	const idProblem = $derived(problems.id === 'empty' && !typed ? null : problems.id);
	const canSave = $derived(!!world && !problems.id && !problems.concepticon);
	const invented = $derived(!draft.wold.trim() && !draft.concepticon.trim());

	const domainOptions = $derived([
		{ value: '', label: t('pojmy.domain.default') },
		...DOMAINS.map((d) => ({ value: d, label: domainLabel(d) }))
	]);
	const classOptions = $derived([
		{ value: '', label: t('pojmy.word_class.none') },
		...WORD_CLASSES.map((w) => ({ value: w, label: t(`pojmy.word_class.${w}` as MessageKey) }))
	]);
	const relatedOptions = $derived([
		{ value: '', label: t('pojmy.related.none') },
		...BASE_CONCEPTS.map((c) => ({ value: c.id, label: baseLabel(c.id) })),
		...custom.filter((c) => c.id !== draft.id.trim()).map((c) => ({ value: c.id, label: customName(c) }))
	]);
	const kindOptions = $derived(RELATION_KINDS.map((k) => ({ value: k, label: t(`pojmy.relation.${k}` as MessageKey) })));

	function reset() {
		editingId = null;
		draft = emptyDraft();
		typed = false;
	}

	function pick(c: CustomConcept) {
		editingId = c.id;
		draft = draftOf(c);
		typed = true;
	}

	function save() {
		if (!canSave) return;
		const spec = conceptOf(draft);
		if (editingId == null) {
			app.edit(t('pojmy.edit.add', { id: spec.id }), (w) => {
				w.concepts = [...customConcepts(w), spec];
			});
		} else {
			const index = custom.findIndex((c) => c.id === editingId);
			if (index >= 0) {
				app.edit(t('pojmy.edit.update', { id: spec.id }), (w) => {
					customConcepts(w)[index] = spec;
				});
			}
		}
		reset();
	}

	function remove() {
		const id = editingId;
		const index = custom.findIndex((c) => c.id === id);
		if (id == null || index < 0) return reset();
		app.edit(t('pojmy.edit.remove', { id }), (w) => {
			const list = customConcepts(w);
			list.splice(index, 1);
			if (!list.length) delete w.concepts;
		});
		reset();
	}
</script>

{#if !world}
	<Screen><Text variant="why">{t('pojmy.no_world')}</Text></Screen>
{:else}
	<Screen columns={['fill', 'fill']} label={t('pojmy.title')}>
		<Area scroll label={t('pojmy.size.title')}>
			<Stack gap={3}>
				<Stack gap={1}>
					<Text variant="caps">{t('pojmy.title')}</Text>
					<Text variant="h1">{t('pojmy.size.title')}</Text>
					<Text variant="why">{t('pojmy.size.intro')}</Text>
				</Stack>

				{#if sizes.length}
					<Table
						caption={t('pojmy.size.caption')}
						head={[{ label: t('pojmy.col.count'), num: true }, { label: t('pojmy.col.what') }, { label: t('pojmy.col.run') }]}
					>
						{#each sizes as n (n)}
							<Tr selected={n === current} onclick={() => choose(n)}>
								<Td num>{number(n)}</Td>
								<Td>{sizeText(n)}</Td>
								<Td>{runText(n)}</Td>
							</Tr>
						{/each}
					</Table>
					<Text variant="why">{t('pojmy.size.note')}</Text>
				{:else}
					<Text variant="why">{t('pojmy.size.offline')}</Text>
				{/if}

				<Stack gap={1}>
					<Text variant="caps">{t('pojmy.domains')}</Text>
					<Ledger termWidth={120}>
						{#each DOMAINS as d (d)}
							<LedgerRow term={domainLabel(d)}>{t(`pojmy.domain_desc.${d}` as MessageKey)}</LedgerRow>
						{/each}
					</Ledger>
				</Stack>

				<Stack gap={1}>
					<Text variant="caps">{t('pojmy.base.caps', { n: BASE_CONCEPTS.length })}</Text>
					<TextInput id="pojmy-search" type="search" bind:value={query} label={t('pojmy.base.search')} placeholder={t('pojmy.base.search')} />
					{#if query.trim()}
						<Text variant="small">{t('pojmy.base.found', { n: baseRows.length, total: BASE_CONCEPTS.length })}</Text>
					{/if}
					{#if baseRows.length}
						<List label={t('pojmy.base.caps', { n: BASE_CONCEPTS.length })}>
							{#each baseRows as c (c.id)}
								<ListItem meta={domainLabel(c.domain)}>{baseLabel(c.id)}</ListItem>
							{/each}
						</List>
					{:else}
						<Text variant="why">{t('pojmy.base.empty')}</Text>
					{/if}
				</Stack>
			</Stack>
		</Area>

		<Area scroll label={t('pojmy.custom.title')}>
			<Stack gap={3}>
				<Stack gap={1}>
					<Text variant="caps">{t('pojmy.custom.caps', { n: custom.length })}</Text>
					<Text variant="h1">{t('pojmy.custom.title')}</Text>
					<Text variant="why">{t('pojmy.custom.intro')}</Text>
				</Stack>

				{#if custom.length}
					<List label={t('pojmy.custom.caps', { n: custom.length })}>
						{#each custom as c (c.id)}
							<ListItem meta={customMeta(c)} current={editingId === c.id} onclick={() => pick(c)}>{customName(c)}</ListItem>
						{/each}
					</List>
				{:else}
					<Text variant="why">{t('pojmy.custom.none')}</Text>
				{/if}

				<Stack gap={1}>
					<Text variant="caps">{editingId == null ? t('pojmy.form.new') : t('pojmy.form.edit', { id: editingId })}</Text>
					<Field
						label={t('pojmy.field.id')}
						for="pojmy-id"
						error={idProblem ? t(`pojmy.err.id_${idProblem}` as MessageKey) : null}
						errorId="pojmy-id-err"
					>
						<TextInput
							id="pojmy-id"
							bind:value={draft.id}
							oninput={() => (typed = true)}
							invalid={!!idProblem}
							describedby={idProblem ? 'pojmy-id-err' : undefined}
						/>
					</Field>
					<Field label={t('pojmy.field.gloss')} for="pojmy-gloss" hint={invented ? t('pojmy.hint.invented') : undefined}>
						<TextInput id="pojmy-gloss" bind:value={draft.gloss} />
					</Field>
					<Field label={t('pojmy.field.domain')} for="pojmy-domain">
						<Select id="pojmy-domain" bind:value={draft.domain} options={domainOptions} />
					</Field>
					<Field label={t('pojmy.field.word_class')} for="pojmy-class">
						<Select id="pojmy-class" bind:value={draft.word_class} options={classOptions} />
					</Field>
					<Field label={t('pojmy.field.wold')} for="pojmy-wold" hint={t('pojmy.hint.wold')}>
						<TextInput id="pojmy-wold" bind:value={draft.wold} />
					</Field>
					<Field
						label={t('pojmy.field.concepticon')}
						for="pojmy-concepticon"
						error={problems.concepticon ? t('pojmy.err.concepticon') : null}
						errorId="pojmy-concepticon-err"
						hint={t('pojmy.hint.concepticon')}
					>
						<TextInput
							id="pojmy-concepticon"
							bind:value={draft.concepticon}
							invalid={problems.concepticon}
							describedby={problems.concepticon ? 'pojmy-concepticon-err' : undefined}
						/>
					</Field>
					<Field label={t('pojmy.field.related')} for="pojmy-related">
						<Select id="pojmy-related" bind:value={draft.related} options={relatedOptions} />
					</Field>
					<Field label={t('pojmy.field.relation')} for="pojmy-relation">
						<Select id="pojmy-relation" bind:value={draft.relation_kind} options={kindOptions} />
					</Field>

					<Cluster gap={2}>
						{#if editingId == null}
							<Button variant="primary" disabled={!canSave} onclick={save}>{t('pojmy.act.add')}</Button>
						{:else}
							<Button variant="primary" disabled={!canSave} onclick={save}>{t('pojmy.act.save')}</Button>
							<Button variant="quiet" onclick={reset}>{t('pojmy.act.cancel')}</Button>
							<Button variant="quiet" onclick={remove}>{t('pojmy.act.delete')}</Button>
						{/if}
					</Cluster>
				</Stack>
			</Stack>
		</Area>
	</Screen>
{/if}
