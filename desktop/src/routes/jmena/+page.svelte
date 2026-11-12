<!-- Jména: generátor jmen sídel a osob podle kraje a epochy (modul jmen enginu, dok. 34).
     Kraj se vybírá na mapě, rok na společné časové ose; jméno se složí ze slov té doby
     a vede se hláskovými změnami do konce běhu. -->
<script lang="ts">
	import {
		Button,
		Card,
		Cluster,
		Disclosure,
		Floating,
		Ipa,
		Kbd,
		Ledger,
		LedgerRow,
		Range,
		Screen,
		Segmented,
		Stack,
		Stage,
		Text,
		WorldMap,
		formatYear,
		type MapLabel,
		type MapVillage
	} from '$lib/ds';
	import { EngineError } from '$lib/engine';
	import { i18n, t, type MessageKey } from '$lib/i18n.svelte';
	import { cityMarkers, geography } from '$lib/model/geography';
	import { causeMessage, epochOf, isPersons, namesAsText, soundChanges, type NameStep, type NamesResult } from '$lib/model/jmena';
	import { frameAt, homeLanguage, lineageNames, lineagePalette } from '$lib/model/languages';
	import { app } from '$lib/state.svelte';

	type Kind = 'place' | 'person';
	let kind = $state<Kind>('place');
	let size = $state<'city' | 'village'>('city');
	let count = $state(6);
	let attempt = $state(0);

	const world = $derived(app.world);
	const result = $derived(app.result);
	const geo = $derived(world ? geography(world, result) : null);
	const endYear = $derived(result?.year ?? world?.end_year ?? 0);
	const year = $derived(Math.round(app.view.year ?? endYear));
	const epochs = $derived(app.frames.map((f) => f.year));
	const epoch = $derived(epochOf(epochs, year));
	const frame = $derived(frameAt(app.frames, year));
	const domainOf = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g.domain])));
	const home = $derived(frame ? homeLanguage(frame.groups, domainOf) : new Map());
	const palette = $derived(result && world ? lineagePalette(world, result) : new Map<string, string>());
	const names = $derived(result && geo ? lineageNames(result, geo.name, i18n.locale, app.frames) : new Map<string, string>());
	const languageName = (lineage: string | null | undefined, code?: string) =>
		(lineage && names.get(lineage)) ?? world?.languages.find((l) => l.id === code)?.name ?? code ?? '—';

	const fill = $derived((v: MapVillage) => palette.get(home.get(v.id)?.lineage ?? '') ?? null);
	const labels = $derived.by(() => {
		if (!geo || !world) return [];
		const out: MapLabel[] = world.regions.filter((r) => geo.regions.length <= 40 || (r.city ?? 0) > 0 || r.id === app.view.region).map((r) => ({ text: geo.name(r.id), region: r.id, kind: 'region' as const, dy: -10 }));
		if (app.view.region) out.push({ text: geo.name(app.view.region), region: app.view.region, kind: 'strong' as const, dy: -12 });
		return out;
	});
	const regionName = $derived(app.view.region && geo ? geo.name(app.view.region) : null);

	// Dotaz jde do enginu při každé změně; starší odpověď pozdější nepřepíše.
	let generated = $state<NamesResult | null>(null);
	let problem = $state<string | null>(null);
	let working = $state(false);
	let copied = $state(false);
	let asked = 0;
	$effect(() => {
		const region = app.view.region;
		const query = { region: region ?? '', year, count, attempt, kind, urban: size === 'city', until: endYear };
		copied = false;
		if (!region || !result) {
			generated = null;
			problem = null;
			return;
		}
		const ticket = ++asked;
		working = true;
		app
			.names(query)
			.then((r) => {
				if (ticket !== asked) return;
				generated = r;
				problem = null;
			})
			.catch((error: unknown) => {
				if (ticket !== asked) return;
				generated = null;
				const message = error instanceof EngineError || error instanceof Error ? error.message : String(error);
				problem =
					message === 'no_engine'
						? t('jmena.no_engine')
						: message.includes('modul jmen')
							? t('jmena.no_module')
							: t('jmena.error', { error: message });
			})
			.finally(() => {
				if (ticket === asked) working = false;
			});
	});

	const tradition = (key: string) => {
		const label = t(`jmena.tr.${key}` as MessageKey);
		return label === `jmena.tr.${key}` ? key : label;
	};
	function cause(step: NameStep): string {
		const m = causeMessage(step.cause);
		return 'text' in m ? m.text : t(m.key as MessageKey, m.params);
	}
	async function copy() {
		if (!generated) return;
		try {
			await navigator.clipboard.writeText(namesAsText(generated));
			copied = true;
		} catch {
			copied = false;
		}
	}
</script>

{#if !world || !geo}
	<Screen><Text variant="why">{t('check.running')}</Text></Screen>
{:else if !result}
	<Screen><Stack gap={3}><Text variant="h1">{t('shell.nav.jmena')}</Text><Text variant="why">{t('jmena.no_result')}</Text></Stack></Screen>
{:else}
	<Screen columns={['fill', 400]} label={t('jmena.title', { region: regionName ?? '—', year: formatYear(year) })}>
		<Stage label={t('jmena.map', { year: formatYear(year) })}>
			<WorldMap
				regions={geo.regions}
				villages={geo.villages}
				label={t('jmena.map', { year: formatYear(year) })}
				{fill}
				fillAlpha={0.45}
				selected={app.view.region}
				{labels}
				markers={cityMarkers(result)}
				onpick={(r) => (app.view.region = r)}
			/>
			{#snippet br()}
				<Floating><Text variant="small"><Kbd>←</Kbd><Kbd>→</Kbd> {t('atlas.keys')}</Text></Floating>
			{/snippet}
		</Stage>

		<Card label={t('jmena.caps', { year: formatYear(year) })}>
			<Stack gap={1}>
				<Text variant="caps">{t('jmena.caps', { year: formatYear(year) })}</Text>
				<Text variant="h1">{regionName ?? t('jmena.pick_title')}</Text>
				{#if !app.view.region}<Text variant="why">{t('jmena.pick')}</Text>{/if}
			</Stack>
			<Stack gap={2}>
				<Segmented
					label={t('jmena.kind')}
					bind:value={kind}
					options={(['place', 'person'] as const).map((k) => ({ value: k, label: t(`jmena.kind.${k}` as MessageKey) }))}
				/>
				{#if kind === 'place'}
					<Segmented
						label={t('jmena.size')}
						bind:value={size}
						options={(['city', 'village'] as const).map((s) => ({ value: s, label: t(`jmena.size.${s}` as MessageKey) }))}
					/>
				{/if}
				<Stack gap={0}>
					<Text variant="small">{t('jmena.count', { n: count })}</Text>
					<Range bind:value={count} min={1} max={12} label={t('jmena.count', { n: count })} />
				</Stack>
				<Cluster gap={2}>
					<Button disabled={!app.view.region} onclick={() => attempt++}>{t('jmena.again')}</Button>
					<Button variant="quiet" disabled={!generated?.names.length} onclick={copy}>{copied ? t('jmena.copied') : t('jmena.copy')}</Button>
				</Cluster>
			</Stack>

			{#if problem}
				<Text tone="red">{problem}</Text>
			{:else if working && !generated}
				<Text variant="why">{t('jmena.working')}</Text>
			{:else if generated && isPersons(generated)}
				<Stack gap={1}>
					<Text variant="why"
						>{t('jmena.person_note', { year: formatYear(generated.year), from: formatYear(generated.words_from), language: languageName(generated.lineage, generated.language) })}</Text
					>
					<Ledger termWidth={90}>
						<LedgerRow term={t('jmena.tradition')}
							>{generated.tradition_label ?? tradition(generated.tradition)}{#if generated.tradition_since != null}{' '}<Text variant="why" as="span">{t('jmena.tradition_since', { year: formatYear(generated.tradition_since) })}</Text>{/if}</LedgerRow
						>
					</Ledger>
				</Stack>
				{#if !generated.names.length}<Text variant="why">{t('jmena.none')}</Text>{/if}
				<Stack gap={2}>
					{#each generated.names as n (n.name)}
						<Stack gap={0}>
							<Text variant="h3">{n.name}</Text>
							<Text><Ipa text={n.ipa} slashes /></Text>
							{#if n.meaning}<Text variant="why">{n.meaning}</Text>{/if}
						</Stack>
					{/each}
				</Stack>
			{:else if generated}
				{@const first = generated.names[0]}
				<Stack gap={1}>
					<Text variant="why"
						>{t('jmena.place_note', {
							year: formatYear(generated.year),
							from: formatYear(first?.founded.words_from ?? epoch ?? generated.year),
							language: first ? languageName(first.founded.lineage, first.founded.language) : '—',
							until: formatYear(generated.until)
						})}</Text
					>
					<Ledger termWidth={90}>
						<LedgerRow term={t('jmena.tradition')}>{tradition(generated.tradition)}</LedgerRow>
					</Ledger>
				</Stack>
				{#if !generated.names.length}<Text variant="why">{t('jmena.none')}</Text>{/if}
				<Stack gap={3}>
					{#each generated.names as n (n.name)}
						{@const changes = soundChanges(n.timeline)}
						<Stack gap={1}>
							<Cluster justify="between" align="baseline">
								<Text variant="h3">{n.name}</Text>
								<Text variant="small" tone="muted">{t('jmena.today', { year: formatYear(generated.until) })} · {languageName(n.lineage, n.language)}</Text>
							</Cluster>
							<Text><Ipa text={n.ipa} slashes /></Text>
							<Text variant="small"
								>{t('jmena.founded', { year: formatYear(n.founded.year) })}{' '}<b>{n.founded.name}</b>{' '}<Ipa text={n.founded.ipa} slashes />{' '}<Text variant="why" as="span">{t('jmena.meaning', { meaning: n.founded.meaning })}</Text></Text
							>
							{#if n.timeline.length}
								<Disclosure>
									{#snippet summary()}{t('jmena.timeline')} · {t('jmena.changes', { n: changes })}{/snippet}
									<Ledger termWidth={70}>
										{#each n.timeline as step, i (i)}
											<LedgerRow term={formatYear(step.year)}
												><Ipa text={step.ipa} />{' '}{step.name}{' '}<Text variant="why" as="span">{cause(step)}</Text></LedgerRow
											>
										{/each}
									</Ledger>
								</Disclosure>
							{:else}
								<Text variant="why">{t('jmena.unchanged')}</Text>
							{/if}
						</Stack>
					{/each}
				</Stack>
			{/if}
		</Card>
	</Screen>
{/if}
