<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { ArrowLeft, BookOpen, Globe2 } from 'lucide-svelte';
	import { onMount } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import TimelineEventEditor from '$lib/TimelineEventEditor.svelte';
	import { loadProject, projectState, removeHistoricalEvent, upsertHistoricalEvent } from '$lib/state.svelte';

	let ready = $state(false);

	onMount(async () => {
		await loadProject($page.params.id ?? 'default');
		ready = true;
	});
</script>

<svelte:head><title>CEE | Časová osa světa</title></svelte:head>

{#if !ready}
	<div class="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Načítám časovou osu…</div>
{:else}
	<div class="min-h-screen bg-background">
		<header class="flex items-center justify-between border-b px-5 py-3">
			<div class="flex items-center gap-3"><Button variant="ghost" size="sm" onclick={() => goto(`/project/${$page.params.id}/map`)}><ArrowLeft class="mr-1 h-4 w-4" />Zpět do projektu</Button><div class="h-5 w-px bg-border"></div><div><h1 class="font-semibold">Časová osa světa</h1><p class="text-xs text-muted-foreground">Události a jejich intervaly</p></div></div>
			<div class="flex items-center gap-2"><Button variant="outline" size="sm" onclick={() => goto(`/project/${$page.params.id}/world`)}><Globe2 class="mr-1 h-4 w-4" />Mapa</Button><Button variant="outline" size="sm" onclick={() => goto(`/project/${$page.params.id}/genealogy`)}><BookOpen class="mr-1 h-4 w-4" />Rodokmen</Button></div>
		</header>
		<main class="mx-auto max-w-7xl p-4 lg:p-6">
			<TimelineEventEditor events={projectState.worldModel.events} languages={projectState.worldModel.languages} onSave={upsertHistoricalEvent} onDelete={removeHistoricalEvent} />
		</main>
	</div>
{/if}
