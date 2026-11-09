<!-- Projekty (úvodní obrazovka): otevřený projekt se souhrnem a stavem běhu, odkazy na Svět a Atlas,
     ukázkové světy ze static/projects a otevření souboru .cee. Nic nenabízí, co aplikace neumí. -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { Area, Button, Cluster, FilePicker, Floating, Ledger, LedgerRow, List, ListItem, Screen, Stack, Text, formatYear } from '$lib/ds';
	import { number, t } from '$lib/i18n.svelte';
	import { baseName, inApp } from '$lib/files';
	import { SAMPLES, parseProject, summarize, type WorldSummary } from '$lib/model/projekty';
	import { app, type WorldSpec } from '$lib/state.svelte';

	// Ukázky: svět se načte při startu kvůli počtům; otevření použije kopii, aby původní zůstal nedotčený.
	const sampleWorlds = new Map<string, WorldSpec>();
	let counts = $state<Record<string, WorldSummary>>({});
	let notice = $state<{ text: string; bad: boolean } | null>(null);

	onMount(async () => {
		for (const sample of SAMPLES) {
			try {
				const world = (await (await fetch(`/projects/${sample.file}`)).json()) as WorldSpec;
				sampleWorlds.set(sample.id, world);
				counts[sample.id] = summarize(world);
			} catch {
				// Ukázka chybí: řádek zůstane bez počtů a jde otevřít jen když se načte.
			}
		}
	});

	const current = $derived(app.world ? summarize(app.world) : null);

	const runText = $derived.by(() => {
		if (app.running && app.run) return { text: t('projekty.run_running', { year: formatYear(app.run.year), pct: Math.round(app.run.progress * 100) }), bad: false };
		if (app.run?.status === 'failed') return { text: t('projekty.run_failed', { error: app.run.error ?? '' }), bad: true };
		if (app.stale) return { text: t('projekty.run_stale'), bad: true };
		if (app.result) return { text: t('projekty.run_done'), bad: false };
		if (app.run?.status === 'cancelled') return { text: t('projekty.run_cancelled'), bad: false };
		return { text: t('projekty.run_none'), bad: false };
	});

	const engineText = $derived.by(() => {
		const phase = app.engineState.phase;
		if (phase === 'connecting') return t('projekty.engine_connecting');
		if (phase === 'offline') return t('projekty.engine_offline');
		if (phase === 'outdated') return t('projekty.engine_outdated');
		return t('projekty.engine_ready');
	});

	// Přepsání otevřeného projektu bez uložení by zahodilo práci; ptáme se jen když je co zahodit.
	const mayReplace = () =>
		app.discardChanges({ title: t('shell.discard_title'), message: t('shell.discard_message'), confirm: t('shell.discard_confirm'), cancel: t('shell.discard_cancel') });
	const app_ = inApp();

	async function openDialog() {
		if (!(await mayReplace())) return;
		try {
			if (await app.openDialog()) notice = { text: t('projekty.opened', { name: app.fileName ?? '' }), bad: false };
		} catch (error) {
			notice = { text: String(error), bad: true };
		}
	}
	async function openRecent(path: string) {
		if (!(await mayReplace())) return;
		try {
			await app.openPath(path);
			notice = { text: t('projekty.opened', { name: baseName(path) }), bad: false };
		} catch (error) {
			notice = { text: String(error), bad: true };
		}
	}
	async function save(as = false) {
		try {
			if (await app.save(as)) notice = { text: t('project.saved'), bad: false };
		} catch (error) {
			notice = { text: String(error), bad: true };
		}
	}
	const when = (seconds: number) => new Date(seconds * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'numeric', year: 'numeric' });

	async function openSample(id: string) {
		const sample = SAMPLES.find((s) => s.id === id);
		if (!sample || !(await mayReplace())) return;
		let world = sampleWorlds.get(id);
		if (!world) {
			try {
				world = (await (await fetch(`/projects/${sample.file}`)).json()) as WorldSpec;
				sampleWorlds.set(id, world);
			} catch {
				notice = { text: t('projekty.sample_bad'), bad: true };
				return;
			}
		}
		app.load(structuredClone(world), sample.file);
		notice = { text: t('projekty.opened', { name: world.name ?? sample.file }), bad: false };
	}

	async function openFile(file: File) {
		if (!(await mayReplace())) return;
		try {
			const world = parseProject(JSON.parse(await file.text()));
			if (!world) throw new Error('format');
			app.load(world, file.name);
			notice = { text: t('projekty.opened', { name: file.name }), bad: false };
		} catch {
			notice = { text: t('projekty.file_bad'), bad: true };
		}
	}
</script>

<Screen columns={['fill', 360]} label={t('projekty.title')}>
	<Area label={t('projekty.title')} scroll>
		<Stack gap={4}>
			<Stack gap={2}>
				<Text variant="h1">{t('projekty.title')}</Text>
				<Text variant="why">{t('projekty.why')}</Text>
			</Stack>

			<Stack gap={3}>
				<Text variant="caps">{t('projekty.open_caps')}</Text>
				{#if current}
					<Text variant="h2">{current.name ?? t('projekty.untitled')}</Text>
					<Ledger termWidth={120}>
						<LedgerRow term={t('projekty.years_row')}>{t('projekty.span', { from: formatYear(current.start), to: formatYear(current.end) })}</LedgerRow>
						<LedgerRow term={t('projekty.regions')}>{number(current.regions)}</LedgerRow>
						<LedgerRow term={t('projekty.cities')}>{number(current.cities)}</LedgerRow>
						<LedgerRow term={t('projekty.languages')}>{number(current.languages)}</LedgerRow>
						<LedgerRow term={t('projekty.events')}>{number(current.events)}</LedgerRow>
						<LedgerRow term={t('projekty.file_row')}>{app.filePath ?? app.fileName ?? t('projekty.file_unsaved')}</LedgerRow>
						<LedgerRow term={t('projekty.run_row')}><Text tone={runText.bad ? 'red' : undefined} as="span">{runText.text}</Text></LedgerRow>
					</Ledger>
					{#if app.dirty}<Text variant="why">{t('projekty.dirty')}</Text>{/if}
					<Cluster gap={2}>
						<Button variant="primary" href="/svet" disabled={!app.world}>{t('projekty.continue_world')}</Button>
						<Button href="/atlas" disabled={!app.world}>{t('projekty.continue_atlas')}</Button>
						<Button icon="save" onclick={() => save()} disabled={!app.world}>{t('projekty.save')}</Button>
						{#if app_}<Button variant="quiet" onclick={() => save(true)} disabled={!app.world}>{t('projekty.save_as')}</Button>{/if}
					</Cluster>
					{#if app_}<Text variant="why">{t('projekty.save_note')}</Text>{/if}
				{:else}
					<Text variant="why">{t('projekty.none')}</Text>
				{/if}
			</Stack>

			{#if app_ && app.recent.length}
				<Stack gap={2}>
					<Text variant="caps">{t('projekty.recent')}</Text>
					<List label={t('projekty.recent')}>
						{#each app.recent as item (item.path)}
							{#if item.exists}
								<ListItem
									onclick={() => openRecent(item.path)}
									current={app.filePath === item.path}
									meta={`${when(item.opened)}${item.runs ? ` · ${t('projekty.recent_runs', { n: item.runs })}` : ''}`}
								>
									<Stack gap={1}>
										<Text variant="h3">{item.name ?? baseName(item.path)}</Text>
										<Text variant="small">{item.path}</Text>
									</Stack>
								</ListItem>
							{:else}
								<ListItem>
									<Cluster gap={2} justify="between">
										<Text variant="why" as="span">{t('projekty.recent_missing', { name: item.name ?? baseName(item.path) })}</Text>
										<Button variant="quiet" onclick={() => app.forgetRecent(item.path)}>{t('projekty.recent_forget')}</Button>
									</Cluster>
								</ListItem>
							{/if}
						{/each}
					</List>
				</Stack>
			{/if}

			<Stack gap={2}>
				<Text variant="caps">{t('projekty.samples')}</Text>
				<List label={t('projekty.samples')}>
					{#each SAMPLES as sample (sample.id)}
						{@const c = counts[sample.id]}
						<ListItem onclick={() => openSample(sample.id)} current={app.fileName === sample.file} meta={t('projekty.sample_open')}>
							<Stack gap={1}>
								<Text variant="h3">{c?.name ?? sample.id}</Text>
								{#if c}<Text variant="small">{t('projekty.sample_counts', { regions: c.regions, cities: c.cities, languages: c.languages, events: c.events })}</Text>{/if}
							</Stack>
						</ListItem>
					{/each}
				</List>
			</Stack>
		</Stack>
	</Area>

	<Area label={t('projekty.file')} scroll>
		<Stack gap={2}>
			<Text variant="caps">{t('projekty.file')}</Text>
			<Cluster>
				{#if app_}
					<Button icon="open" onclick={openDialog}>{t('projekty.file_open')}</Button>
				{:else}
					<FilePicker accept=".json,application/json" onfile={openFile} label={t('projekty.file_open')}>{t('projekty.file_open')}</FilePicker>
				{/if}
			</Cluster>
			<Text variant="why">{t('projekty.file_note')}</Text>
			{#if notice}<Text variant="why" tone={notice.bad ? 'red' : undefined}>{notice.text}</Text>{/if}
		</Stack>

		<Floating>
			<Text variant="caps">{t('projekty.engine')}</Text>
			<Text variant="small">{engineText}</Text>
		</Floating>
	</Area>
</Screen>
