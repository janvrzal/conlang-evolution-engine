<script lang="ts">
	import { i18n, t, type MessageKey } from '$lib/i18n.svelte';
	import { languageFromEndonym } from '$lib/naming';
	import { app } from '$lib/state.svelte';

	const regions = $derived(app.world?.regions ?? []);
	// Jméno jazyka v popisu světa je jeho vlastní jméno; česky se z něj tvoří -ština.
	const languageName = (id?: string) => {
		const name = app.world?.languages.find((l) => l.id === id)?.name;
		return name ? languageFromEndonym(name, i18n.locale) : (id ?? '—');
	};
	const regionName = (id: string) => regions.find((r) => r.id === id)?.name ?? id;
</script>

<section class="page">
	<div>
		<h1>{t('world.regions')} <small>{regions.length}</small></h1>
		<p class="why">{t('world.editor_soon')}</p>
		<table class="ledger">
			<thead>
				<tr>
					<th>{t('world.region')}</th>
					<th>{t('world.language')}</th>
					<th>{t('world.terrain')}</th>
					<th>{t('world.identity')}</th>
					<th>{t('world.villages')}</th>
					<th>{t('world.neighbours')}</th>
				</tr>
			</thead>
			<tbody>
				{#each regions as region (region.id)}
					<tr>
						<td><b>{region.name ?? region.id}</b></td>
						<td>{languageName(region.language)}</td>
						<td>{t(`terrain.${region.terrain ?? 'plain'}` as MessageKey)}</td>
						<td>{t(`identity.${region.identity ?? 'shared'}` as MessageKey)}</td>
						<td>{region.villages ?? 4}</td>
						<td class="why">{(region.neighbours ?? []).map(regionName).join(', ')}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<aside>
		<div class="caps">{t('check.title')}</div>
		{#if app.checking}
			<p class="why">{t('check.running')}</p>
		{:else if app.issues && app.issues.length === 0}
			<p>{t('check.ok')}</p>
		{:else if app.issues}
			<ul class="issues">
				{#each app.issues as issue (issue.path + issue.message)}
					<li><code>{issue.path}</code> {issue.message}</li>
				{/each}
			</ul>
			<p class="why">{t('check.engine_language')}</p>
		{/if}
	</aside>
</section>

<style>
	.page {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 320px;
		gap: 24px;
	}
	h1 {
		margin: 0 0 4px;
		font-size: 24px;
	}
	h1 small {
		font-size: 14px;
		color: var(--ink-2);
		font-weight: 400;
	}
	.issues {
		padding-left: 18px;
		font-size: 14px;
	}
	.issues code {
		font-size: 12px;
		color: var(--warn);
	}
	@media (max-width: 900px) {
		.page {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
