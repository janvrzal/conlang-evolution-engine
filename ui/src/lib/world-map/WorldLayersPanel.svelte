<script lang="ts">
	import { Eye, EyeOff } from 'lucide-svelte';
	import type { WorldLayerId } from './types';
	let { layers = { languages: true, regions: true, settlements: true, routes: false, politics: false }, onToggle }: { layers?: Record<WorldLayerId, boolean>; onToggle?: (layer: WorldLayerId, visible: boolean) => void } = $props();
	const labels: Record<WorldLayerId, string> = { languages: 'Jazykové oblasti', regions: 'Regiony', settlements: 'Sídla', routes: 'Obchodní trasy', politics: 'Politické hranice' };
</script>

<div class="space-y-1" aria-label="Vrstvy mapy">
	{#each Object.keys(labels) as id}
		{@const layer = id as WorldLayerId}
		<button class="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-sm hover:bg-muted" onclick={() => onToggle?.(layer, !layers[layer])}>
			<span>{labels[layer]}</span>{#if layers[layer]}<Eye class="h-4 w-4 text-muted-foreground" />{:else}<EyeOff class="h-4 w-4 text-muted-foreground" />{/if}
		</button>
	{/each}
</div>
