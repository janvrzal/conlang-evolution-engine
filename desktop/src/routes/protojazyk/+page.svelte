<script lang="ts">
	import { i18n, t } from '$lib/i18n.svelte';
	import { languageFromEndonym } from '$lib/naming';
	import { app } from '$lib/state.svelte';
</script>

<section>
	<h1>{t('proto.languages')}</h1>
	<table class="ledger">
		<thead>
			<tr>
				<th></th>
				<th>{t('proto.consonants')}</th>
				<th>{t('proto.vowels')}</th>
				<th>{t('proto.stress')}</th>
				<th>{t('proto.grammar')}</th>
				<th></th>
			</tr>
		</thead>
		<tbody>
			{#each app.world?.languages ?? [] as language (language.id)}
				<tr>
					<td><b>{language.name ? languageFromEndonym(language.name, i18n.locale) : language.id}</b></td>
					<td class="ipa">{language.consonants?.join(' ') ?? t('proto.default_inventory')}</td>
					<td class="ipa">{language.vowels?.join(' ') ?? t('proto.default_inventory')}</td>
					<td>{language.stress ?? 'penult'}</td>
					<td>{language.grammar ?? 'default'}</td>
					<td class="why">{t('proto.words', { n: Object.keys(language.words ?? {}).length })}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</section>

<style>
	h1 {
		margin: 0 0 10px;
		font-size: 24px;
	}
	.ipa {
		font-size: 17px;
	}
</style>
