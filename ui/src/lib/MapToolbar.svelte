<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Select } from '$lib/components/ui/select';
	import { t } from '$lib/i18n.svelte';
	import { GitCommitHorizontal, MousePointer2, Route, Trash2 } from 'lucide-svelte';

	let {
		activeTool = $bindable<'interact' | 'relationship' | 'route'>(),
		relationshipType = $bindable<'inheritance' | 'contact'>(),
		selectedEdgeId = null,
		onDeleteEdge
	}: {
		activeTool: 'interact' | 'relationship' | 'route';
		relationshipType: 'inheritance' | 'contact';
		selectedEdgeId?: string | null;
		onDeleteEdge: () => void;
	} = $props();
</script>

<div
	class="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex bg-card rounded-md border shadow-sm p-1 gap-1"
>
	<Button
		variant={activeTool === 'interact' ? 'default' : 'ghost'}
		size="sm"
		class="px-3"
		onclick={() => (activeTool = 'interact')}
		title={t('moveHint')}
	>
		<MousePointer2 class="w-4 h-4 mr-2" />{t('interaction')}
	</Button>
	<Button
		variant={activeTool === 'route' ? 'default' : 'ghost'}
		size="sm"
		class="px-3"
		onclick={() => (activeTool = 'route')}
		title="Klikáním do mapy kreslí body vybrané obchodní trasy"
	>
		<Route class="w-4 h-4 mr-2" />Trasa
	</Button>
	<Button
		variant={activeTool === 'relationship' ? 'default' : 'ghost'}
		size="sm"
		class="px-3"
		onclick={() => (activeTool = 'relationship')}
		title={t('relationshipHint')}
	>
		<GitCommitHorizontal class="w-4 h-4 mr-2" />{t('relationship')}
	</Button>
	{#if activeTool === 'relationship'}
		<Select class="h-8 w-36" bind:value={relationshipType} title={t('relationship')}>
			<option value="inheritance">{t('inheritance')}</option>
			<option value="contact">{t('contact')}</option>
		</Select>
	{/if}
	{#if selectedEdgeId}
		<div class="w-px bg-border mx-1"></div>
		<Button
			variant="ghost"
			size="sm"
			class="px-3 text-destructive hover:text-destructive"
			onclick={onDeleteEdge}
			title="Smazat vybrané spojení (Delete)"
		>
			<Trash2 class="w-4 h-4 mr-2" />Smazat spojení
		</Button>
	{/if}
</div>
