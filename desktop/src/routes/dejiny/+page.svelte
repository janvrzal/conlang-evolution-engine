<script lang="ts">
	import { t, type MessageKey } from '$lib/i18n.svelte';
	import { app } from '$lib/state.svelte';

	const regionName = (id: string) => app.world?.regions.find((r) => r.id === id)?.name ?? id;
	function detail(event: Record<string, unknown>): string {
		const parts: string[] = [];
		if (typeof event.name === 'string') parts.push(event.name);
		for (const key of ['state', 'of', 'source', 'capital'])
			if (typeof event[key] === 'string') parts.push(regionName(event[key] as string));
		if (Array.isArray(event.regions)) parts.push((event.regions as string[]).map(regionName).join(', '));
		for (const key of ['policy', 'border', 'identity', 'strength', 'coverage', 'spread'])
			if (typeof event[key] === 'string') parts.push(event[key] as string);
		return parts.join(' · ');
	}
</script>

<section>
	<h1>{t('history.events')}</h1>
	{#if !app.world?.events.length}
		<p class="why">{t('history.none')}</p>
	{:else}
		<table class="ledger">
			<thead><tr><th>{t('history.year')}</th><th>{t('history.kind')}</th><th>{t('history.detail')}</th></tr></thead>
			<tbody>
				{#each app.world.events as event, index (index)}
					<tr>
						<td class="year">{event.year}</td>
						<td>{t(`kind.${event.kind}` as MessageKey)}</td>
						<td class="why">{detail(event)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>

<style>
	h1 {
		margin: 0 0 10px;
		font-size: 24px;
	}
	.year {
		font-variant-numeric: tabular-nums;
		width: 70px;
	}
</style>
