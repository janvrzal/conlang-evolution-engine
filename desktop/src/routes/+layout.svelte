<script lang="ts">
	import '@fontsource/piazzolla/400.css';
	import '@fontsource/piazzolla/400-italic.css';
	import '@fontsource/piazzolla/500.css';
	import '@fontsource/piazzolla/700.css';
	import '$lib/tokens.css';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { i18n, t, type Locale, type MessageKey } from '$lib/i18n.svelte';
	import { app } from '$lib/state.svelte';

	let { children } = $props();

	const STEPS: { path: string; key: MessageKey }[] = [
		{ path: '/svet', key: 'step.world' },
		{ path: '/protojazyk', key: 'step.proto' },
		{ path: '/dejiny', key: 'step.history' },
		{ path: '/vysledky', key: 'step.results' },
		{ path: '/vetve', key: 'step.branches' }
	];

	let fileInput: HTMLInputElement;
	let notice = $state<string | null>(null);

	onMount(async () => {
		document.documentElement.lang = i18n.locale;
		await app.connect();
		if (!app.world) await app.loadStarter();
	});

	async function open(event: Event) {
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
		if (!file) return;
		try {
			const world = JSON.parse(await file.text());
			if (world.format !== 'cee-v2-world/1') throw new Error('format');
			app.load(world, file.name);
			notice = t('project.opened', { name: file.name });
		} catch {
			notice = t('project.bad_file');
		}
	}

	function save() {
		if (!app.world) return;
		// V prohlížeči se soubor stáhne; v Tauri ho později uloží dialog na disk.
		const blob = new Blob([JSON.stringify(app.world, null, 1)], { type: 'application/json' });
		const link = document.createElement('a');
		link.href = URL.createObjectURL(blob);
		link.download = app.fileName ?? 'svet.cee.json';
		link.click();
		URL.revokeObjectURL(link.href);
		app.dirty = false;
		notice = t('project.saved');
	}

	const years = $derived(app.world ? app.world.end_year - (app.world.start_year ?? 0) : 0);
	const errors = $derived(app.issues?.length ?? 0);
</script>

<div class="app">
	<header class="top">
		<div class="project">
			<span class="name">{app.world?.name ?? t('project.untitled')}</span>
			<small>{t('project.years', { years })}{app.dirty ? ` · ${t('project.unsaved')}` : ''}</small>
		</div>
		<nav aria-label={t('step.nav')}>
			<ol class="path">
				{#each STEPS as step, index (step.path)}
					<li>
						<a href={step.path} aria-current={page.url.pathname.startsWith(step.path) ? 'page' : undefined}
							><b>{index + 1}</b>{t(step.key)}</a
						>
					</li>
				{/each}
			</ol>
		</nav>
		<div class="tools">
			<button class="btn" onclick={() => fileInput.click()}>{t('project.open')}</button>
			<input bind:this={fileInput} type="file" accept=".json,application/json" hidden onchange={open} />
			<button class="btn" onclick={save} disabled={!app.world}>{t('project.save')}</button>
			<div class="locale" role="group" aria-label={t('locale.switch')}>
				{#each ['cs', 'en'] as Locale[] as code (code)}
					<button aria-pressed={i18n.locale === code} onclick={() => (i18n.locale = code)}>{code.toUpperCase()}</button>
				{/each}
			</div>
		</div>
	</header>

	<main class="main">
		{#if app.engineState.phase === 'offline' || app.engineState.phase === 'outdated'}
			<div class="banner" role="alert">
				<b>{app.engineState.phase === 'offline'
						? t('engine.offline')
						: t('engine.outdated', { have: app.engineState.health.api_revision, need: 9 })}</b>
				<span class="why">{t('engine.hint')}</span>
				<button class="btn" onclick={() => app.connect()}>{t('engine.retry')}</button>
			</div>
		{/if}
		{@render children()}
	</main>

	<footer class="foot">
		<span class="engine" data-phase={app.engineState.phase}>
			{app.engineState.phase === 'ready'
				? `${t('engine.ready')} · ${app.engineState.health.version}`
				: app.engineState.phase === 'connecting'
					? t('engine.connecting')
					: t('engine.offline')}
		</span>
		<span class="check">
			{#if app.checking}{t('check.running')}{:else if app.issues && errors === 0}{t('check.ok')}{:else if errors}<a
					href="/svet">{t('check.title')}: {errors}</a
				>{/if}
		</span>
		{#if notice}<span class="why">{notice}</span>{/if}
		<span class="spacer"></span>
		{#if app.run?.status === 'running'}
			<span class="progress"
				><i style="width:{Math.round(app.run.progress * 100)}%"></i><b
					>{t('run.progress', { year: Math.round(app.run.year), end: app.run.end_year })}</b
				></span
			>
			<button class="btn" onclick={() => app.cancel()}>{t('run.cancel')}</button>
		{:else}
			<button
				class="btn primary"
				disabled={app.engineState.phase !== 'ready' || !app.world || errors > 0}
				onclick={async () => {
					await app.start();
				}}>{t('run.start', { years })}</button
			>
		{/if}
	</footer>
</div>

<style>
	.app {
		height: 100%;
		display: grid;
		grid-template-rows: auto minmax(0, 1fr) auto;
		padding: 10px 16px;
		gap: 10px;
	}
	.top {
		display: flex;
		align-items: baseline;
		gap: 28px;
		flex-wrap: wrap;
		border-bottom: 1px solid var(--ink);
		padding-bottom: 8px;
	}
	.project .name {
		font-size: 22px;
		font-style: italic;
	}
	.project small {
		font-size: 12px;
		color: var(--ink-2);
		margin-left: 8px;
	}
	.path {
		display: flex;
		gap: 4px;
		list-style: none;
		margin: 0;
		padding: 0;
		flex-wrap: wrap;
	}
	.path li {
		display: flex;
		align-items: baseline;
		gap: 4px;
	}
	.path li + li::before {
		content: '';
		width: 22px;
		border-top: 1px dotted var(--ink-2);
		align-self: center;
	}
	.path a {
		color: var(--ink-2);
		text-decoration: none;
		padding: 2px 4px;
	}
	.path a b {
		font-weight: 500;
		font-size: 11px;
		margin-right: 4px;
	}
	.path a[aria-current='page'] {
		color: var(--ink);
		box-shadow: inset 0 -2px 0 var(--red);
	}
	.tools {
		margin-left: auto;
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.locale {
		display: flex;
		border: 1px solid var(--ink);
		border-radius: 2px;
		overflow: hidden;
	}
	.locale button {
		border: 0;
		background: none;
		padding: 4px 8px;
		cursor: pointer;
		font-size: 12px;
	}
	.locale button[aria-pressed='true'] {
		background: var(--ink);
		color: var(--panel);
	}
	.main {
		min-height: 0;
		overflow: auto;
	}
	.banner {
		display: flex;
		gap: 14px;
		align-items: center;
		flex-wrap: wrap;
		border: 1px solid var(--warn);
		padding: 8px 12px;
		margin-bottom: 12px;
		border-radius: 2px;
	}
	.foot {
		display: flex;
		gap: 18px;
		align-items: center;
		border-top: 1px solid var(--rule);
		padding-top: 8px;
		font-size: 13px;
		color: var(--ink-2);
		flex-wrap: wrap;
	}
	.foot a {
		color: var(--warn);
	}
	.engine::before {
		content: '';
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		margin-right: 6px;
		background: var(--ink-3);
	}
	.engine[data-phase='ready']::before {
		background: var(--l2);
	}
	.engine[data-phase='offline']::before,
	.engine[data-phase='outdated']::before {
		background: var(--warn);
	}
	.spacer {
		margin-left: auto;
	}
	.progress {
		position: relative;
		width: 260px;
		height: 22px;
		border: 1px solid var(--ink);
		border-radius: 2px;
		overflow: hidden;
		display: grid;
		place-items: center;
	}
	.progress i {
		position: absolute;
		inset: 0 auto 0 0;
		background: var(--ink-3);
	}
	.progress b {
		position: relative;
		font-weight: 500;
		color: var(--ink);
		font-variant-numeric: tabular-nums;
	}
</style>
