<script lang="ts">
	import type { WorldMapPoint } from './types';
	let { selected = null }: { selected?: WorldMapPoint | null } = $props();
</script>

<div class="space-y-3" aria-label="Geografický inspektor">
	{#if selected}
		<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Vybraný bod</p><h2 class="text-lg font-semibold">{selected.label}</h2></div>
		<div class="grid grid-cols-2 gap-2 text-sm"><div class="rounded border p-2"><p class="text-xs text-muted-foreground">Typ</p><p>{selected.kind ?? 'jazyková oblast'}</p></div><div class="rounded border p-2"><p class="text-xs text-muted-foreground">Rodina</p><p>{selected.family ?? 'neuvedena'}</p></div></div>
		<p class="text-xs text-muted-foreground">Tento panel pouze čte geografickou entitu. Genealogie a simulace se upravují v samostatných obrazovkách.</p>
	{:else}<p class="text-sm text-muted-foreground">Vyberte bod na mapě. Inspektor zobrazí jen geografický kontext.</p>{/if}
</div>
