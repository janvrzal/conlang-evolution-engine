<!-- Kostra aplikace: lišta Zadání | Výsledek, stav běhu, pruhy hlášení, pata zadání s ověřením
     a společná časová osa obrazovek Výsledku. Skládá se jen z komponent $lib/ds. -->
<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import {
		AppBar,
		BrandMark,
		Banner,
		ConfirmDialog,
		Button,
		CheckBadge,
		FilePicker,
		Footer,
		IssueList,
		Popover,
		Shell,
		Spacer,
		Splash,
		Text,
		TimeAxis,
		Toast,
		Working,
		formatYear,
		type AxisMarker,
		type IssueItem,
		type NavItem
	} from '$lib/ds';
	import { API_REVISION } from '$lib/engine';
	import { inApp } from '$lib/files';
	import { i18n, number, t, type MessageKey } from '$lib/i18n.svelte';
	import { frameAt, speakers, varietiesAt } from '$lib/model/languages';
	import { app } from '$lib/state.svelte';
	import { dockProgress } from '$lib/dock';

	let { children } = $props();

	const SPEC = ['svet', 'protojazyky', 'pojmy', 'dejiny', 'model'] as const;
	const RESULTS = ['atlas', 'jazyky', 'slova', 'kronika', 'cokdyby'] as const;
	const href = (id: string) => (id === 'cokdyby' ? '/co-kdyby' : `/${id}`);
	const route = $derived(page.url.pathname.split('/')[1] ?? '');
	const inSpec = $derived((SPEC as readonly string[]).includes(route));
	const inResults = $derived((RESULTS as readonly string[]).includes(route === 'co-kdyby' ? 'cokdyby' : route));

	const spec: NavItem[] = $derived(
		SPEC.map((id) => ({ href: href(id), label: t(`shell.nav.${id}` as MessageKey), current: route === id, mark: id === 'model' ? null : app.world ? 'done' : 'todo' }))
	);
	const results: NavItem[] = $derived(
		RESULTS.map((id) => ({ href: href(id), label: t(`shell.nav.${id}` as MessageKey), current: href(id) === `/${route}`, mark: app.stale && id !== 'cokdyby' ? 'stale' : null }))
	);

	const from = $derived(formatYear(app.world?.start_year ?? 0));
	const to = $derived(formatYear(app.world?.end_year ?? 0));
	const errors = $derived(app.errors.length);
	const warnings = $derived(app.warnings.length);
	let checkOpen = $state(false);
	let notice = $state<string | null>(null);

	// Výběr z adresy (odkazy z hlášení, sdílení pohledu): ?region= &year= &concept= &lineage= &event= &lang= &all=1
	$effect(() => {
		const q = page.url.searchParams;
		const lang = q.get('lang');
		if (lang === 'cs' || lang === 'en') i18n.locale = lang;
		if (q.has('region')) app.view.region = q.get('region');
		if (q.has('year')) app.view.year = Number(q.get('year'));
		if (q.has('concept')) app.view.concept = q.get('concept')!;
		if (q.has('lineage')) app.view.lineage = q.get('lineage');
		if (q.has('event')) app.view.event = Number(q.get('event'));
		if (q.has('all')) app.view.allLanguages = q.get('all') === '1';
	});

	// Úvodní animace jednou za otevření okna (obnovení stránky ji nepřehraje znovu).
	let splashing = $state(false);
	function splashDone() {
		splashing = false;
		try {
			sessionStorage.setItem('cee.splash', '1');
		} catch {
			// úložiště nedostupné: animace se příště přehraje znovu
		}
	}
	// Konec běhu: značka v liště přehraje vlnu (hotovo) nebo uschne (selhal).
	let wasRunning = false;
	let finished = $state(0);
	$effect(() => {
		if (app.running) wasRunning = true;
		else if (wasRunning) {
			wasRunning = false;
			finished = Date.now();
		}
	});
	// Postup běhu i v Docku (macOS) a na hlavním panelu (Windows).
	$effect(() => {
		if (inApp()) dockProgress(app.running ? (app.run?.progress ?? 0) : null);
	});

	onMount(async () => {
		document.documentElement.lang = i18n.locale;
		try {
			splashing = !sessionStorage.getItem('cee.splash');
		} catch {
			splashing = true;
		}
		// vývoj: ?fixture=talvera&branch=talvera-bez-politiky načte vzorek skutečného běhu
		const fixture = import.meta.env.DEV ? page.url.searchParams.get('fixture') : null;
		if (fixture) await app.loadFixture(fixture, page.url.searchParams.get('branch') ?? undefined);
		else if (!app.world) await app.loadStarter();
		await app.connect();
	});

	// Hláška „Vrátit“ po každé úpravě zadání.
	let toast = $state<string | null>(null);
	let toastTimer: ReturnType<typeof setTimeout> | null = null;
	$effect(() => {
		const edit = app.lastEdit;
		if (!edit) return;
		toast = edit;
		if (toastTimer) clearTimeout(toastTimer);
		toastTimer = setTimeout(() => (toast = null), 4000);
	});

	// ⌘Z / ⇧⌘Z zpět a znovu (mimo textová pole), ⌘S uložit, ⇧⌘S uložit jako, ⌘O otevřít
	function key(event: KeyboardEvent) {
		const mod = event.metaKey || event.ctrlKey;
		if (!mod) return;
		const k = event.key.toLowerCase();
		if (k === 's') {
			event.preventDefault();
			void save(event.shiftKey);
		} else if (k === 'o') {
			event.preventDefault();
			void openDialog();
		} else if (k === 'z') {
			const target = event.target as HTMLElement;
			if (target.closest('input, textarea, select')) return;
			event.preventDefault();
			if (event.shiftKey) app.redo();
			else app.undo();
		}
	}

	const discardTexts = () => ({ title: t('shell.discard_title'), message: t('shell.discard_message'), confirm: t('shell.discard_confirm'), cancel: t('shell.discard_cancel') });

	/** Otevření v prohlížeči (výběr souboru). */
	async function openFile(file: File) {
		if (!(await app.discardChanges(discardTexts()))) return;
		try {
			const parsed = JSON.parse(await file.text());
			const world = parsed.format === 'cee-project/1' ? parsed.world : parsed;
			if (world?.format !== 'cee-v2-world/1') throw new Error('format');
			app.load(world, file.name);
			notice = t('project.opened', { name: file.name });
		} catch {
			notice = t('project.bad_file');
		}
	}
	/** Otevření v aplikaci (dialog). */
	async function openDialog() {
		if (!inApp() || !(await app.discardChanges(discardTexts()))) return;
		try {
			if (await app.openDialog()) notice = t('project.opened', { name: app.fileName ?? '' });
		} catch (error) {
			notice = String(error);
		}
	}
	async function save(as = false) {
		try {
			if (await app.save(as)) notice = t('project.saved');
		} catch (error) {
			notice = String(error);
		}
	}

	// Hlášení ověření s místem v zadání a odkazem na obrazovku.
	const issueItems: IssueItem[] = $derived(
		(app.issues ?? []).map((issue) => {
			const [head, index] = issue.path.split('.');
			const n = Number(index);
			let place: string | undefined, link: string | undefined;
			if (head === 'events' && app.world?.events[n]) {
				const ev = app.world.events[n];
				place = t('shell.place.events', { what: `${t(`kind.${ev.kind}` as MessageKey) ?? ev.kind} ${formatYear(ev.year)}` });
				link = `/dejiny?event=${n}`;
			} else if (head === 'regions' && app.world?.regions[n]) {
				place = t('shell.place.regions', { what: app.world.regions[n].name ?? app.world.regions[n].id });
				link = `/svet?region=${app.world.regions[n].id}`;
			} else if (head === 'languages' && app.world?.languages[n]) {
				place = t('shell.place.languages', { what: app.world.languages[n].name ?? app.world.languages[n].id });
				link = '/protojazyky';
			} else if (head === 'vocabulary' || head === 'concepts') {
				place = t('shell.place.vocabulary');
				link = '/pojmy';
			} else if (head === 'parameters') {
				place = t('shell.place.parameters');
				link = '/model';
			}
			// česky přesná zpráva enginu; v jiném jazyce šablona podle stálého kódu (dok. 36)
			const key = `issue.${issue.code}` as MessageKey;
			const message = i18n.locale !== 'cs' && issue.code && t(key) !== key ? t(key, issue.args ?? {}) : issue.message;
			return { severity: issue.severity === 'warning' ? 'warning' : 'error', place, href: link, message, code: issue.path };
		})
	);

	// Časová osa Výsledku: rok, značky dějin autora, hustota = počet jazyků v čase.
	const endYear = $derived(app.result?.year ?? app.run?.end_year ?? app.world?.end_year ?? 0);
	const startYear = $derived(app.world?.start_year ?? 0);
	const until = $derived(app.running ? Math.round(app.run?.year ?? startYear) : undefined);
	let year = $state(0);
	$effect(() => {
		year = app.view.year ?? until ?? endYear;
	});
	const AXIS_KINDS = new Set(['state', 'collapse', 'secession', 'conquest', 'language_policy']);
	const markers: AxisMarker[] = $derived(
		(app.world?.events ?? [])
			.filter((e) => AXIS_KINDS.has(e.kind) && (e.kind !== 'language_policy' || e.policy === 'enforced'))
			.map((e) => ({ year: e.year, label: `${t(`kind.${e.kind}` as MessageKey)}${typeof e.name === 'string' ? ` ${e.name}` : ''}` }))
	);
	const density = $derived.by(() => {
		const counts = app.frames.map((f) => Object.keys(f.languages).length), max = Math.max(1, ...counts);
		return counts.map((c) => c / max);
	});
	const domainOf = $derived(new Map((app.result?.groups ?? []).map((g) => [g.id, g.domain])));
	const axisSummary = $derived.by(() => {
		const f = frameAt(app.frames, year);
		if (!f) return '';
		const sp = [...speakers(f.groups, domainOf).values()].reduce((a, b) => a + b, 0);
		const common = { dialects: f.dialects.length, speakers: number(sp), states: f.states.length };
		if (app.view.allLanguages || !app.result || !app.world) return t('shell.axis_sum', { langs: Object.keys(f.languages).length, ...common });
		const v = varietiesAt(app.world, app.result, f.groups, domainOf);
		return t('shell.axis_sum_var', { langs: v.major.length, small: v.host.size + v.orphans.length, ...common });
	});
</script>

<svelte:window onkeydown={key} />

{#if splashing}<Splash generation={(n) => t('shell.splash_generation', { n })} subtitle="Conlang Evolution Engine" onend={splashDone} />{/if}

<Shell>
	{#snippet bar()}
		<AppBar
			project={{ name: app.world?.name ?? t('project.untitled'), note: app.dirty ? t('shell.unsaved') : t('shell.saved') }}
			{spec}
			{results}
			specLabel={t('shell.spec')}
			resultsLabel={t('shell.results')}
			progress={app.running ? (app.run?.progress ?? 0) : null}
		>
			{#snippet status()}
				{#if app.running && app.run}
					<Working />
					<span>{t('shell.running', { year: formatYear(app.run.year), from, to, pct: Math.round(app.run.progress * 100) })}</span>
					<Button onclick={() => app.cancel()}>{t('shell.stop')}</Button>
				{:else if app.run?.status === 'failed'}
					<BrandMark mode="wither" size={18} />
					<Text tone="red" as="span">{t('shell.failed', { error: app.run.error ?? '' })}</Text>
					<Button variant="primary" disabled={errors > 0} onclick={() => app.start()}>{t('shell.rerun', { from, to })}</Button>
				{:else if app.stale}
					<Text tone="red" as="span">{t('shell.stale')}</Text>
					<Button variant="primary" disabled={errors > 0} onclick={() => app.start()}>{t('shell.rerun', { from, to })}</Button>
				{:else if app.result}
					{#key finished}<BrandMark mode={finished ? 'wave' : 'mark'} size={18} />{/key}
					<span>{t('shell.fresh', { from, to, seconds: Math.round(app.run?.seconds ?? 0) })}</span>
				{:else}
					<span>{app.run?.status === 'cancelled' ? t('shell.cancelled') : t('shell.no_run')}</span>
					<Button variant="primary" disabled={errors > 0 || app.engineState.phase !== 'ready'} title={errors ? t('shell.fix_first') : undefined} onclick={() => app.start()}
						>{t('shell.run', { from, to })}</Button
					>
				{/if}
			{/snippet}
			{#snippet tools()}
				{#if inApp()}
					<Button icon="open" label={t('shell.open')} title="{t('shell.open')} (⌘O)" onclick={openDialog} />
				{:else}
					<FilePicker accept=".json,application/json" onfile={openFile} label={t('shell.open')} />
				{/if}
				<Button icon="save" label={t('shell.save')} title="{t('shell.save')} (⌘S, ⇧⌘S jako)" onclick={() => save()} disabled={!app.world} />
				<Button variant="quiet" label={t('shell.locale')} title={t('shell.locale')} onclick={() => (i18n.locale = i18n.locale === 'cs' ? 'en' : 'cs')}
					>{i18n.locale === 'cs' ? 'EN' : 'CS'}</Button
				>
			{/snippet}
		</AppBar>
	{/snippet}

	{#snippet banner()}
		{#if app.engineState.phase === 'offline' || app.engineState.phase === 'outdated'}
			<Banner tone="error">
				<b>{app.engineState.phase === 'offline' ? t('shell.offline') : t('shell.outdated', { have: app.engineState.health.api_revision, need: API_REVISION })}</b>
				{t('shell.offline_hint')}
				{#snippet actions()}<Button onclick={() => app.connect()}>{t('shell.retry')}</Button>{/snippet}
			</Banner>
		{:else if app.stale && inResults}
			<Banner tone="stale">
				{t('shell.stale_banner', { edit: app.lastEdit ?? '' })}
				{#snippet actions()}
					<Button variant="quiet" href="/dejiny">{t('shell.what_changed')}</Button>
					<Button variant="primary" disabled={errors > 0} onclick={() => app.start()}>{t('shell.rerun', { from, to })}</Button>
				{/snippet}
			</Banner>
		{/if}
	{/snippet}

	{@render children()}

	{#snippet footer()}
		{#if inSpec}
			<Footer label={t('shell.check')}>
				<Popover label={t('shell.check')} open={checkOpen && issueItems.length > 0}>
					<Text variant="caps">{t('shell.check')}</Text>
					<IssueList items={issueItems} />
					<Text variant="why">{t('shell.check_note')}</Text>
				</Popover>
				{#if app.world}<span>{t('shell.summary', { regions: app.world.regions.length, langs: app.world.languages.length, events: app.world.events.length })}</span>{/if}
				<CheckBadge
					ok={errors === 0}
					text={app.checking ? t('shell.check_running') : errors ? t('shell.check_bad', { e: errors, w: warnings }) : t('shell.check_ok', { w: warnings })}
					expanded={checkOpen}
					onclick={() => (checkOpen = !checkOpen)}
				/>
				<Button variant="quiet" icon="undo" disabled={!app.canUndo} onclick={() => app.undo()}>{t('shell.undo')}</Button>
				<Button variant="quiet" icon="redo" disabled={!app.canRedo} onclick={() => app.redo()}>{t('shell.redo')}</Button>
				{#if notice || app.notice}<Text variant="why" as="span">{notice ?? app.notice}</Text>{/if}
				<Spacer />
				{#if errors}<Text variant="why" as="span">{t('shell.fix_first')}</Text>{/if}
				<Button variant="primary" disabled={errors > 0 || app.running || app.engineState.phase !== 'ready'} href={errors ? undefined : '/atlas'} onclick={() => app.start()}
					>{t('shell.run', { from, to })}</Button
				>
			</Footer>
		{:else if inResults && (app.result || app.frames.length)}
			<TimeAxis
				start={startYear}
				end={endYear}
				bind:value={year}
				{until}
				{density}
				{markers}
				branchFrom={route === 'co-kdyby' && app.branch?.branchYear != null && Number.isFinite(app.branch.branchYear) ? app.branch.branchYear : undefined}
				label={t('shell.axis')}
				playLabel={t('shell.play')}
				pauseLabel={t('shell.pause')}
				clockNote={until != null ? t('shell.axis_until', { year: formatYear(until) }) : year >= endYear ? t('shell.axis_end') : t('shell.axis_year')}
				onchange={(y) => (app.view.year = y)}
			>
				{#snippet summary()}{axisSummary}{#if density.length}<Text variant="why">{t('shell.axis_density')}</Text>{/if}{/snippet}
			</TimeAxis>
		{/if}
		{#if app.confirmRequest}
			<ConfirmDialog
				open
				title={app.confirmRequest.title}
				message={app.confirmRequest.message}
				confirmLabel={app.confirmRequest.confirm}
				cancelLabel={app.confirmRequest.cancel}
				danger={app.confirmRequest.danger}
				onconfirm={() => app.confirmRequest?.resolve(true)}
				oncancel={() => app.confirmRequest?.resolve(false)}
			/>
		{/if}
		{#if toast}
			<Toast
				message={toast}
				actionLabel={t('shell.undo_toast')}
				onaction={() => {
					app.undo();
					toast = null;
				}}
				shortcut="Ctrl Z"
			/>
		{/if}
	{/snippet}
</Shell>
