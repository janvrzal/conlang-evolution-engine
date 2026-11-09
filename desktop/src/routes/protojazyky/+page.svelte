<!-- Protojazyky zadání: seznam, hlásky a slabiky, přízvuk, mluvnice, změny na startu, slova a vlastní jméno.
     Úpravy jdou přes app.edit; po běhu karta ukáže jazyky, které z protojazyka vznikly. -->
<script lang="ts">
	import { page } from '$app/state';
	import {
		Area,
		Button,
		Card,
		Chip,
		Cluster,
		Field,
		Ipa,
		List,
		ListItem,
		Range,
		Screen,
		Segmented,
		Select,
		Stack,
		Swatch,
		Table,
		Tabs,
		Td,
		Text,
		TextInput,
		Tr,
		familyColor,
		formatYear
	} from '$lib/ds';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { conceptLabel } from '$lib/model/concepts';
	import { geography } from '$lib/model/geography';
	import { frameAt, lineageFamilies, lineageNames, lineagePalette } from '$lib/model/languages';
	import {
		BASIC_CONCEPTS,
		CONSTRUCTION_KINDS,
		FUNCTIONS,
		GRAMMARS,
		KNOWN_CONSONANTS,
		MANNERS,
		PLACES,
		PROCESS_FAMILIES,
		STRESSES,
		SYLLABLES,
		TONES,
		VOWELS,
		cell,
		descendants,
		extraSegments,
		formRows,
		newLanguageId,
		protoForms,
		regionCount,
		toggleSegment,
		wordConcepts,
		type FormRow,
		type ProtoLanguage
	} from '$lib/model/protojazyky';
	import { app } from '$lib/state.svelte';

	type Tab = 'sounds' | 'stress' | 'grammar' | 'changes' | 'words';
	const TABS: Tab[] = ['sounds', 'stress', 'grammar', 'changes', 'words'];
	// ?tab= a ?proto= otevřou kartu a protojazyk přímo (sdílení pohledu)
	const fromUrl = page.url.searchParams.get('tab');
	let tab = $state<Tab>(TABS.find((x) => x === fromUrl) ?? 'sounds');
	let selected = $state<string | null>(page.url.searchParams.get('proto'));

	const world = $derived(app.world);
	const result = $derived(app.result);
	const languages = $derived(world?.languages ?? []);
	const index = $derived(Math.max(0, languages.findIndex((l) => l.id === selected)));
	const lang = $derived((languages[index] ?? null) as ProtoLanguage | null);

	/** Úprava vybraného protojazyka: zapíše se do zadání a kostra z toho udělá Zpět. */
	function change(label: MessageKey, fn: (l: ProtoLanguage) => void) {
		const id = lang?.id;
		if (!id) return;
		app.edit(t(label), (w) => {
			const l = w.languages.find((x) => x.id === id);
			if (l) fn(l as ProtoLanguage);
		});
	}
	function add() {
		if (!world) return;
		const id = newLanguageId(world);
		app.edit(t('protojazyky.edit.add'), (w) => void w.languages.push({ id, name: t('protojazyky.new_name') }));
		selected = id;
	}
	const proto = (name: string | undefined, id: string) => t('protojazyky.proto', { name: name ?? id });

	// ---------- hlásky ----------
	let newConsonant = $state<string | number>('');
	let newVowel = $state<string | number>('');
	const consonants = $derived(lang?.consonants ?? []);
	const vowels = $derived(lang?.vowels ?? []);
	const extraConsonants = $derived(extraSegments(consonants, KNOWN_CONSONANTS));
	const vowelChips = $derived([...VOWELS, ...extraSegments(vowels, VOWELS)]);
	function addSegment(kind: 'consonants' | 'vowels') {
		const seg = String(kind === 'consonants' ? newConsonant : newVowel).trim();
		if (!seg) return;
		if (kind === 'consonants') newConsonant = '';
		else newVowel = '';
		if ((lang?.[kind] ?? []).includes(seg)) return;
		change(kind === 'consonants' ? 'protojazyky.edit.consonant' : 'protojazyky.edit.vowel', (l) => (l[kind] = [...(l[kind] ?? []), seg]));
	}
	const syllableValue = $derived(lang?.syllables ?? 'random');

	// ---------- mluvnice ----------
	let constructionFn = $state<string>('PAST');
	let constructionKind = $state<string>('synthetic');
	let constructionSource = $state<string | number>('');
	const constructions = $derived(Object.entries(lang?.constructions ?? {}));
	function addConstruction() {
		const fn = constructionFn, kind = constructionKind, source = String(constructionSource).trim();
		constructionSource = '';
		change('protojazyky.edit.construction', (l) => (l.constructions = { ...(l.constructions ?? {}), [fn]: { kind, source: source || null } }));
	}
	function removeConstruction(fn: string) {
		change('protojazyky.edit.construction', (l) => {
			const rest = { ...(l.constructions ?? {}) };
			delete rest[fn];
			l.constructions = rest;
		});
	}

	// ---------- změny na startu ----------
	let processFamily = $state<string>('coda_loss');
	let processLabel = $state<string | number>('m → ∅ / V_#');
	let processShare = $state(0.3);
	function addProcess() {
		const family = processFamily, label = String(processLabel).trim(), share = Math.round(processShare * 100) / 100;
		if (!label) return;
		change('protojazyky.edit.process', (l) => (l.processes = [...(l.processes ?? []), { family, label, share }]));
	}

	// ---------- slova a jméno ----------
	let query = $state<string | number>('');
	let newWord = $state<string | number>('');
	let endonymAdd = $state('');
	const concepts = $derived(lang ? wordConcepts(lang, result) : []);
	// tvary z běhu (proto_lexicon) a zdroj každého slova: autor, nebo engine
	const forms = $derived(protoForms(result, lang?.id));
	const formsStale = $derived(!!result && app.stale);
	const startYear = $derived(result ? formatYear(result.start_year) : '');
	const basic = $derived(lang ? formRows(lang, forms, BASIC_CONCEPTS).filter((r): r is FormRow & { form: string } => r.form !== null) : []);
	const basicOf = (origin: FormRow['origin']) => basic.filter((r) => r.origin === origin).map((r) => `‘${conceptLabel(r.concept, i18n.locale)}’`).join(', ');
	const rows = $derived.by(() => {
		const q = String(query).trim().toLowerCase();
		return (lang ? formRows(lang, forms, concepts) : [])
			.map((r) => ({ ...r, id: r.concept, label: conceptLabel(r.concept, i18n.locale) }))
			.filter((r) => !q || r.label.toLowerCase().includes(q) || r.concept.includes(q))
			.sort((a, b) => a.label.localeCompare(b.label, i18n.locale));
	});
	const endonym = $derived(lang?.endonym ?? []);
	function setWord(concept: string, value: string) {
		const form = value.trim();
		change('protojazyky.edit.word', (l) => {
			const words = { ...(l.words ?? {}) };
			if (form) words[concept] = form;
			else delete words[concept];
			l.words = words;
		});
	}
	function addWord() {
		const id = String(newWord).trim();
		if (!id) return;
		newWord = '';
		query = '';
		change('protojazyky.edit.word', (l) => (l.words = { [id]: '', ...(l.words ?? {}) }));
	}
	const authorWords = $derived(Object.entries(lang?.words ?? {}).filter(([, v]) => v));

	// ---------- výsledek: potomci ----------
	const geo = $derived(world ? geography(world, result) : null);
	const frame = $derived(result ? frameAt(app.frames, result.year) : null);
	const families = $derived(world && result ? lineageFamilies(world, result) : new Map<string, number>());
	const names = $derived(result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const palette = $derived(world && result ? lineagePalette(world, result) : new Map<string, string>());
	const children = $derived(descendants(frame, result, families, index));
	const shown = $derived(children.slice(0, 4));
	const rest = $derived(children.slice(4));
	const totalPeople = $derived(children.reduce((a, c) => a + c.speakers, 0));
	const counts = $derived(result?.event_counts);
	const href = (id: string) => `/jazyky?lineage=${encodeURIComponent(id)}`;
</script>

{#if !world}
	<Screen><Text variant="why">{t('check.running')}</Text></Screen>
{:else}
	<Screen columns={[270, 'fill']} label={t('protojazyky.title')}>
		<Card label={t('protojazyky.list')}>
			<Stack gap={2}>
				<Text variant="caps">{t('protojazyky.list')}</Text>
				{#if languages.length}
					<List label={t('protojazyky.list')}>
						{#each languages as l, i (l.id)}
							<ListItem current={i === index} onclick={() => (selected = l.id)} meta={t('protojazyky.regions', { n: regionCount(world, l.id) })}>
								<Swatch color={familyColor(i)} />{proto(l.name, l.id)}
							</ListItem>
						{/each}
					</List>
				{:else}
					<Text variant="why">{t('protojazyky.empty')}</Text>
				{/if}
				<Button variant="quiet" onclick={add}>{t('protojazyky.add')}</Button>
				<Text variant="why">{t('protojazyky.add_note')}</Text>
			</Stack>
			{#if lang}
				<Stack gap={2}>
					<Text variant="caps">{t('protojazyky.desc', { name: proto(lang.name, lang.id) })}</Text>
					{#if result && frame}
						{#if app.stale}<Text variant="why" tone="red">{t('protojazyky.desc_stale')}</Text>{/if}
						{#if children.length}
							<List label={t('protojazyky.desc', { name: proto(lang.name, lang.id) })}>
								{#each shown as c (c.id)}
									<ListItem href={href(c.id)} meta={number(c.speakers)}>
										<Swatch color={palette.get(c.id) ?? 'var(--ink-3)'} />{names.get(c.id) ?? c.id}
									</ListItem>
								{/each}
								{#if rest.length}
									<ListItem href={href(children[0].id)} meta={number(rest.reduce((a, c) => a + c.speakers, 0))}>
										<Text variant="why" as="span">{t('protojazyky.desc_more', { n: rest.length })}</Text>
									</ListItem>
								{/if}
							</List>
							<Button variant="quiet" href={href(children[0].id)}>{t('protojazyky.desc_all')}</Button>
						{:else}
							<Text variant="why">{t('protojazyky.desc_none')}</Text>
						{/if}
						<Text variant="why">{t('protojazyky.desc_year', { year: formatYear(frame.year), langs: children.length, people: number(totalPeople) })}</Text>
					{:else}
						<Text variant="why">{t('protojazyky.desc_wait')}</Text>
					{/if}
				</Stack>
			{/if}
		</Card>

		{#if lang}
			<Area scroll label={proto(lang.name, lang.id)}>
				<Stack gap={3}>
					<Cluster gap={4} align="baseline">
						<Text variant="h1">{proto(lang.name, lang.id)}</Text>
						{#if endonym.length}
							<Text variant="why">{t('protojazyky.endonym_made')} {endonym.map((c) => `‘${conceptLabel(c, i18n.locale)}’`).join(' + ')}</Text>
						{/if}
					</Cluster>
					<Tabs label={t('protojazyky.tabs')} bind:value={tab} tabs={TABS.map((id) => ({ id, label: t(`protojazyky.tab.${id}` as MessageKey) }))} />

					{#if tab === 'sounds'}
						<Screen columns={['fill', 300]} rows={['auto']}>
							<Area>
								<Stack gap={2}>
									<Text variant="h2">{t('protojazyky.consonants')} <Text variant="why" as="span">{consonants.length}</Text></Text>
									<Area scroll>
									<Table caption={t('protojazyky.chart')} head={[{ label: '' }, ...PLACES.map((p) => ({ label: t(`protojazyky.place.${p.id}` as MessageKey) }))]}>
										{#each MANNERS as m (m.id)}
											<Tr>
												<Td tone="muted">{t(`protojazyky.manner.${m.id}` as MessageKey)}</Td>
												{#each PLACES as p (p.id)}
													<Td>
														<Cluster gap={1} wrap={false}>
															{#each cell(p, m) as seg (seg)}
																<Chip state={consonants.includes(seg) ? 'on' : 'off'} onclick={() => change('protojazyky.edit.consonant', (l) => (l.consonants = toggleSegment(l.consonants, seg)))}><Ipa text={seg} size="m" /></Chip>
															{/each}
														</Cluster>
													</Td>
												{/each}
											</Tr>
										{/each}
									</Table>
									</Area>
									<Text variant="why">{t('protojazyky.chart_hint')}</Text>
									<Cluster gap={2} align="center">
										<Text variant="caps">{t('protojazyky.extra')}</Text>
										{#each extraConsonants as seg (seg)}
											<Chip state="on" onclick={() => change('protojazyky.edit.consonant', (l) => (l.consonants = toggleSegment(l.consonants, seg)))}><Ipa text={seg} size="m" /></Chip>
										{:else}
											<Text variant="why">{t('protojazyky.extra_none')}</Text>
										{/each}
										<TextInput width="s" label={t('protojazyky.add_segment')} placeholder={t('protojazyky.add_segment')} bind:value={newConsonant} onchange={() => addSegment('consonants')} />
										<Button onclick={() => addSegment('consonants')}>{t('protojazyky.add_consonant')}</Button>
									</Cluster>
									<Field label={t('protojazyky.syllables')} hint={t('protojazyky.syllables_hint')}>
										<Segmented
											label={t('protojazyky.syllables')}
											value={syllableValue}
											options={SYLLABLES.map((s) => ({ value: s, label: t(`protojazyky.syllables.${s}` as MessageKey) }))}
											onchange={(v) => change('protojazyky.edit.syllables', (l) => (l.syllables = v === 'random' ? null : v))}
										/>
									</Field>
								</Stack>
							</Area>
							<Area>
								<Stack gap={3}>
									<Stack gap={2}>
										<Text variant="h2">{t('protojazyky.vowels')} <Text variant="why" as="span">{vowels.length}</Text></Text>
										<Cluster gap={1}>
											{#each vowelChips as seg (seg)}
												<Chip state={vowels.includes(seg) ? 'on' : 'off'} onclick={() => change('protojazyky.edit.vowel', (l) => (l.vowels = toggleSegment(l.vowels, seg)))}><Ipa text={seg} size="m" /></Chip>
											{/each}
										</Cluster>
										<Cluster gap={2}>
											<TextInput width="s" label={t('protojazyky.add_segment')} placeholder={t('protojazyky.add_segment')} bind:value={newVowel} onchange={() => addSegment('vowels')} />
											<Button onclick={() => addSegment('vowels')}>{t('protojazyky.add_vowel')}</Button>
										</Cluster>
									</Stack>
									<Stack gap={2}>
										<Text variant="h2">{t('protojazyky.tones')}</Text>
										<Cluster gap={1}>
											{#each TONES as tone (tone)}
												<Chip state={lang.tones?.includes(tone) ? 'on' : 'off'} onclick={() => change('protojazyky.edit.tone', (l) => (l.tones = toggleSegment(l.tones, tone)))}><Ipa text={`a${tone}`} size="m" /></Chip>
											{/each}
										</Cluster>
										<Text variant="why">{lang.tones?.length ? t('protojazyky.tones_some', { n: lang.tones.length }) : t('protojazyky.tones_none')}</Text>
									</Stack>
									<Stack gap={2}>
										<Text variant="h2">{t('protojazyky.sound')}</Text>
										{#if basic.length}
											<Text variant="big"><Ipa text={basic.map((r) => r.form).join(' · ')} size="l" /></Text>
											{#if basicOf('engine')}<Text variant="why">{t('protojazyky.sound_from_engine', { list: basicOf('engine'), year: startYear })}</Text>{/if}
											{#if basicOf('author')}<Text variant="why">{t('protojazyky.sound_from_author', { list: basicOf('author') })}</Text>{/if}
											{#if formsStale}<Text variant="why" tone="red">{t('protojazyky.forms_stale')}</Text>{/if}
										{:else}
											<Text variant="why">{t('protojazyky.sound_none')}</Text>
										{/if}
									</Stack>
								</Stack>
							</Area>
						</Screen>
					{:else if tab === 'stress'}
						<Stack gap={2}>
							<Field label={t('protojazyky.stress')} hint={t('protojazyky.stress_hint')}>
								<Segmented
									label={t('protojazyky.stress')}
									value={lang.stress ?? 'penult'}
									options={STRESSES.map((s) => ({ value: s, label: t(`protojazyky.stress.${s}` as MessageKey) }))}
									onchange={(v) => change('protojazyky.edit.stress', (l) => (l.stress = v))}
								/>
							</Field>
							<Field label={t('protojazyky.strength')} hint={t('protojazyky.strength_hint')}>
								<Segmented
									label={t('protojazyky.strength')}
									value={lang.stress_strength ?? 'weak'}
									options={(['weak', 'strong'] as const).map((s) => ({ value: s, label: t(`protojazyky.strength.${s}` as MessageKey) }))}
									onchange={(v) => change('protojazyky.edit.stress', (l) => (l.stress_strength = v))}
								/>
							</Field>
							<Stack gap={1}>
								<Text variant="caps">{t('protojazyky.stress_events')}</Text>
								<Text variant="why">
									{counts ? t('protojazyky.stress_events_n', { rule: number(counts.stress_rule_changed ?? 0), strength: number(counts.stress_strength_changed ?? 0) }) : t('protojazyky.stress_events_none')}
								</Text>
							</Stack>
						</Stack>
					{:else if tab === 'grammar'}
						<Stack gap={2}>
							<Field label={t('protojazyky.grammar')} hint={t(`protojazyky.grammar_hint.${lang.grammar ?? 'default'}` as MessageKey)}>
								<Segmented
									label={t('protojazyky.grammar')}
									value={lang.grammar ?? 'default'}
									options={GRAMMARS.map((g) => ({ value: g, label: t(`protojazyky.grammar.${g}` as MessageKey) }))}
									onchange={(v) => change('protojazyky.edit.grammar', (l) => (l.grammar = v))}
								/>
							</Field>
							<Stack gap={1}>
								<Text variant="caps">{t('protojazyky.constructions')}</Text>
								{#if constructions.length}
									<Table head={[{ label: t('protojazyky.col.function') }, { label: t('protojazyky.col.kind') }, { label: t('protojazyky.col.source') }, { label: '' }]}>
										{#each constructions as [fn, c] (fn)}
											<Tr>
												<Td>{t(`protojazyky.fn.${fn}` as MessageKey)}</Td>
												<Td>{t(`protojazyky.kind.${c.kind}` as MessageKey)}</Td>
												<Td>{c.source ? conceptLabel(c.source, i18n.locale) : '—'}</Td>
												<Td><Button variant="quiet" onclick={() => removeConstruction(fn)}>{t('protojazyky.remove')}</Button></Td>
											</Tr>
										{/each}
									</Table>
								{:else}
									<Text variant="why">{t('protojazyky.constructions_none')}</Text>
								{/if}
								<Cluster gap={2}>
									<Select label={t('protojazyky.col.function')} bind:value={constructionFn} options={FUNCTIONS.map((f) => ({ value: f, label: t(`protojazyky.fn.${f}` as MessageKey) }))} />
									<Select label={t('protojazyky.col.kind')} bind:value={constructionKind} options={CONSTRUCTION_KINDS.map((k) => ({ value: k, label: t(`protojazyky.kind.${k}` as MessageKey) }))} />
									<TextInput width="m" label={t('protojazyky.construction_source')} placeholder={t('protojazyky.construction_source')} bind:value={constructionSource} />
									<Button onclick={addConstruction}>{t('protojazyky.construction_add')}</Button>
								</Cluster>
							</Stack>
							<Field label={t('protojazyky.suffixes')} hint={t('protojazyky.suffixes_hint')}>
								<TextInput
									width="l"
									label={t('protojazyky.suffixes')}
									value={(lang.suffixes ?? []).join(', ')}
									onchange={(v) => change('protojazyky.edit.suffixes', (l) => (l.suffixes = String(v).split(',').map((s) => s.trim()).filter(Boolean)))}
								/>
							</Field>
							{#if lang.endings && Object.keys(lang.endings).length}
								<Text variant="why">{t('protojazyky.endings_in_file', { n: Object.keys(lang.endings).length })}</Text>
							{/if}
						</Stack>
					{:else if tab === 'changes'}
						<Stack gap={2}>
							<Text variant="why">{t('protojazyky.changes_intro')}</Text>
							{#if lang.processes?.length}
								<Table head={[{ label: t('protojazyky.col.change') }, { label: t('protojazyky.col.label') }, { label: t('protojazyky.col.share'), num: true }, { label: '' }]}>
									{#each lang.processes as p, i (i)}
										<Tr>
											<Td>{t(`protojazyky.family.${p.family}` as MessageKey)}</Td>
											<Td ipa>{p.label}</Td>
											<Td num>{Math.round(p.share * 100)} %</Td>
											<Td><Button variant="quiet" onclick={() => change('protojazyky.edit.process', (l) => (l.processes = (l.processes ?? []).filter((_, j) => j !== i)))}>{t('protojazyky.remove')}</Button></Td>
										</Tr>
									{/each}
								</Table>
							{:else}
								<Text variant="why">{t('protojazyky.changes_none')}</Text>
							{/if}
							<Cluster gap={3} align="end">
								<Field label={t('protojazyky.family')}>
									<Select label={t('protojazyky.family')} bind:value={processFamily} options={PROCESS_FAMILIES.map((f) => ({ value: f, label: t(`protojazyky.family.${f}` as MessageKey) }))} />
								</Field>
								<Field label={t('protojazyky.label')}>
									<TextInput width="m" label={t('protojazyky.label')} bind:value={processLabel} />
								</Field>
								<Field label={t('protojazyky.share', { pct: Math.round(processShare * 100) })}>
									<Range label={t('protojazyky.share', { pct: Math.round(processShare * 100) })} bind:value={processShare} min={0.05} max={0.95} step={0.05} />
								</Field>
								<Button onclick={addProcess}>{t('protojazyky.change_add')}</Button>
							</Cluster>
						</Stack>
					{:else}
						<Stack gap={3}>
							<Screen columns={['fill', 'fill']} rows={['auto']}>
								<Area>
									<Stack gap={2}>
										<Text variant="h2">{t('protojazyky.endonym')}</Text>
										<Field label={t('protojazyky.name')}>
											<TextInput width="m" label={t('protojazyky.name')} value={lang.name ?? ''} onchange={(v) => change('protojazyky.edit.name', (l) => (l.name = String(v).trim() || undefined))} />
										</Field>
										<Cluster gap={1}>
											{#each endonym as c, i (c + i)}
												<Chip state="on" title={t('protojazyky.endonym_remove', { concept: conceptLabel(c, i18n.locale) })} onclick={() => change('protojazyky.edit.endonym', (l) => (l.endonym = (l.endonym ?? []).filter((_, j) => j !== i)))}>{conceptLabel(c, i18n.locale)} ×</Chip>
											{/each}
											<Select
												label={t('protojazyky.endonym_add')}
												bind:value={endonymAdd}
												options={[{ value: '', label: t('protojazyky.endonym_add') }, ...concepts.map((c) => ({ value: c, label: conceptLabel(c, i18n.locale) }))]}
												onchange={(v) => {
													if (v) change('protojazyky.edit.endonym', (l) => (l.endonym = [...(l.endonym ?? []), v]));
													endonymAdd = '';
												}}
											/>
										</Cluster>
										<Text variant="why">{t('protojazyky.endonym_hint')}</Text>
									</Stack>
								</Area>
								<Area>
									<Stack gap={2}>
										<Text variant="h2">{t('protojazyky.words')} <Text variant="why" as="span">{authorWords.length}</Text></Text>
										<Text variant="why">{t('protojazyky.words_hint')}</Text>
										{#if !forms}
											<Text variant="why">{t('protojazyky.forms_none')}</Text>
										{:else if formsStale}
											<Text variant="why" tone="red">{t('protojazyky.forms_stale')}</Text>
										{/if}
										<Cluster gap={2}>
											<TextInput type="search" width="m" label={t('protojazyky.words_search')} placeholder={t('protojazyky.words_search')} bind:value={query} />
											<TextInput width="m" label={t('protojazyky.word_new')} placeholder={t('protojazyky.word_new')} bind:value={newWord} onchange={addWord} />
											<Button onclick={addWord}>{t('protojazyky.word_add')}</Button>
										</Cluster>
										<Text variant="why">{t('protojazyky.words_shown', { shown: rows.length, total: concepts.length })}</Text>
									</Stack>
								</Area>
							</Screen>
							<Table head={[{ label: t('protojazyky.col.meaning') }, { label: t('protojazyky.col.engine_form') }, { label: t('protojazyky.col.origin') }, { label: t('protojazyky.col.form') }]}>
								{#each rows as r (r.id)}
									<Tr>
										<Td>{r.label}{#if endonym.includes(r.id)} <Text variant="why" as="span">{t('protojazyky.word_name')}</Text>{/if}</Td>
										<Td ipa>{r.form ?? '—'}</Td>
										<Td tone="muted">{r.origin ? t(`protojazyky.origin.${r.origin}` as MessageKey) : '—'}</Td>
										<Td>
											<TextInput width="m" label={t('protojazyky.word_input', { concept: r.label })} value={lang.words?.[r.id] ?? ''} onchange={(v) => setWord(r.id, String(v))} />
										</Td>
									</Tr>
								{/each}
							</Table>
							{#if !authorWords.length}<Text variant="why">{t('protojazyky.words_none')}</Text>{/if}
						</Stack>
					{/if}
				</Stack>
			</Area>
		{/if}
	</Screen>
{/if}
