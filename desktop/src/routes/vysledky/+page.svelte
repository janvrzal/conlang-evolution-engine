<script lang="ts">
	import { i18n, number, t } from '$lib/i18n.svelte';
	import { dialectNames, languageNames, romanize } from '$lib/naming';
	import { app } from '$lib/state.svelte';

	const result = $derived(app.result);
	const regionName = (id: string) => app.world?.regions.find((r) => r.id === id)?.name ?? id;
	const population = $derived(new Map((result?.groups ?? []).map((g) => [g.id, g.population])));
	// Vymřelý jazyk má poslední vlastní jméno z průběžných snímků.
	const lastEndonym = $derived.by(() => {
		const found = new Map<string, string>();
		for (const frame of app.frames) for (const [id, name] of Object.entries(frame.endonyms ?? {})) if (name) found.set(id, name);
		return found;
	});
	const lineages = $derived(result?.lineages ?? []);
	const names = $derived(
		languageNames(
			lineages.map((l) => ({
				id: l.id,
				parent: l.parent,
				endonym: l.endonym ?? lastEndonym.get(l.id) ?? null,
				origin: l.origin_region ? regionName(l.origin_region) : null
			})),
			i18n.locale
		)
	);
	const color = (index: number) => `var(--l${index % 6})`;
	function dialectsOf(id: string) {
		const facts = (result?.dialect_facts ?? []).filter((d) => d.lineage === id);
		return dialectNames(facts, regionName, i18n.locale).map((name, i) => ({ name, villages: facts[i].groups.length }));
	}
</script>

<section>
	<h1>{t('results.languages')}</h1>
	{#if app.run?.status === 'failed'}
		<p class="why">{t('run.failed')}: {app.run.error}</p>
	{:else if app.run?.status === 'cancelled'}
		<p class="why">{t('run.cancelled')}</p>
	{/if}
	{#if !result}
		<p class="why">{app.run?.status === 'running' ? t('run.progress', { year: Math.round(app.run.year), end: app.run.end_year }) : t('run.none')}</p>
	{:else}
		<p class="why">{t('run.done', { seconds: app.run?.seconds ?? 0 })}</p>
		<ul class="languages">
			{#each lineages as lineage, index (lineage.id)}
				{@const speakers = lineage.groups.reduce((s, g) => s + (population.get(g) ?? 0), 0)}
				{@const endonym = lineage.endonym ?? lastEndonym.get(lineage.id)}
				<li class:dead={!lineage.groups.length}>
					<div class="head">
						<i style="background:{color(index)}"></i>
						<b>{names.get(lineage.id)}</b>
						{#if endonym}<span class="why">{t('results.endonym')} <i>{romanize(endonym)}</i> <span class="ipa">/{endonym}/</span></span>{/if}
					</div>
					<div class="facts why">
						{#if lineage.parent}{t('results.from_parent', { parent: names.get(lineage.parent) ?? '' })} · {/if}
						{t('results.born', { year: lineage.start_year })}
						{#if lineage.end_year != null} · {t('results.extinct', { year: lineage.end_year })}{/if}
						{#if lineage.groups.length} · {t('results.villages', { n: lineage.groups.length })} · {t('results.speakers', { n: number(speakers) })}{/if}
					</div>
					{#if lineage.groups.length}
						<div class="dialects">
							<span class="caps">{t('results.dialects')}</span>
							{#each dialectsOf(lineage.id) as dialect (dialect.name)}
								<span class="chip">{dialect.name} <small>{dialect.villages}</small></span>
							{/each}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	h1 {
		margin: 0 0 4px;
		font-size: 24px;
	}
	.languages {
		list-style: none;
		margin: 14px 0 0;
		padding: 0;
		display: grid;
		gap: 14px;
	}
	.languages li {
		border-bottom: 1px solid var(--rule);
		padding-bottom: 12px;
		display: grid;
		gap: 4px;
	}
	.languages li.dead {
		opacity: 0.6;
	}
	.head {
		display: flex;
		gap: 10px;
		align-items: baseline;
		flex-wrap: wrap;
	}
	.head > i {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		display: inline-block;
	}
	.head b {
		font-size: 19px;
	}
	.ipa {
		font-style: normal;
		font-size: 15px;
	}
	.dialects {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		align-items: center;
	}
	.chip {
		border: 1px solid var(--rule);
		background: var(--field);
		padding: 1px 8px;
		border-radius: 2px;
		font-size: 13px;
	}
	.chip small {
		color: var(--ink-2);
	}
</style>
