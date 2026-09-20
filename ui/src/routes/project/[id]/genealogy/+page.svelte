<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { ArrowLeft } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import GenealogyView from '$lib/GenealogyView.svelte';
	import { loadProject, projectState } from '$lib/state.svelte';

	let ready = $state(false);

	onMount(async () => {
		await loadProject($page.params.id ?? 'default');
		ready = true;
	});
</script>

<svelte:head><title>{projectState.name} · Rodokmen</title></svelte:head>

{#if !ready}
	<div class="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Načítám rodokmen…</div>
{:else}
	<div class="min-h-screen bg-background">
		<div class="flex items-center gap-2 border-b px-4 py-3 md:px-6">
			<Button variant="ghost" size="sm" onclick={() => goto(`/project/${encodeURIComponent($page.params.id ?? '')}/map`)}><ArrowLeft class="h-4 w-4" /> Mapa</Button>
			<span class="text-sm text-muted-foreground">/</span>
			<span class="text-sm font-medium">{projectState.name}</span>
		</div>
		<GenealogyView snapshots={projectState.snapshots} timeSteps={projectState.timeSteps} focusId={$page.url.searchParams.get('focus')} />
	</div>
{/if}
