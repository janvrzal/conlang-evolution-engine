<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';

	export type PendingHomophony = {
		decision_id: string;
		year: number;
		language_id: string;
		pressure: number;
		reason: string;
		status: string;
		winner_id?: string;
		loser_id?: string;
		reviewState?: 'reviewing';
	};

	let {
		items = [],
		onResolve
	}: {
		items?: PendingHomophony[];
		onResolve: (item: PendingHomophony, action: 'review' | 'dismiss') => void;
	} = $props();
</script>

<Card class="w-80 max-h-[45vh] overflow-auto">
	<CardHeader><CardTitle>Kolize k rozhodnutí</CardTitle></CardHeader>
	<CardContent class="space-y-3">
		{#if items.length === 0}
			<p class="text-sm text-muted-foreground">V aktuálním běhu nejsou žádné nevyřešené kolize.</p>
		{:else}
			{#each items as item (item.decision_id)}
				<div class="rounded-md border p-3 space-y-2">
					<p class="text-sm font-medium">
						Rok {item.year} · tlak {Math.round(item.pressure * 100)} %
					</p>
					{#if item.winner_id && item.loser_id}
						<p class="font-mono text-xs">{item.winner_id} ↔ {item.loser_id}</p>
					{/if}
					<p class="text-xs text-muted-foreground">{item.reason}</p>
					<div class="flex gap-2">
						<Button size="sm" onclick={() => onResolve(item, 'review')}
							>{item.reviewState ? 'Znovu otevřít' : 'Otevřít správu'}</Button
						>
						<Button size="sm" variant="outline" onclick={() => onResolve(item, 'dismiss')}
							>Ponechat kolizi</Button
						>
					</div>
				</div>
			{/each}
		{/if}
	</CardContent>
</Card>
