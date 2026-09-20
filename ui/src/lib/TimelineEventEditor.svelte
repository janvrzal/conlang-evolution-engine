<script lang="ts">
	import { CalendarPlus, Pencil, Plus, Trash2 } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import type { HistoricalEvent, HistoricalEventKind, LanguageEntity } from '$lib/world-model';
	import {
		eventParticipants,
		eventToDraft,
		HISTORICAL_EVENT_KINDS,
		HISTORICAL_EVENT_LABELS,
		newHistoricalEventDraft,
		sortHistoricalEvents,
		type HistoricalEventDraft
	} from '$lib/timeline-events';

	let {
		events = [],
		languages = [],
		onSave,
		onDelete
	}: {
		events?: HistoricalEvent[];
		languages?: LanguageEntity[];
		onSave?: (draft: HistoricalEventDraft) => { ok: true; event: HistoricalEvent } | { ok: false; errors: string[] };
		onDelete?: (id: string) => void;
	} = $props();

	let selectedId = $state<string | null>(null);
	let draft = $state<HistoricalEventDraft>(newHistoricalEventDraft());
	let errors = $state<string[]>([]);
	let participantInput = $state('');
	const languageNames = $derived(new Map(languages.map((language) => [language.id, language.name])));
	const orderedEvents = $derived(sortHistoricalEvents(events));

	function selectEvent(event: HistoricalEvent) {
		selectedId = event.id;
		draft = eventToDraft(event);
		errors = [];
	}

	function startNew() {
		selectedId = null;
		draft = newHistoricalEventDraft();
		errors = [];
		participantInput = '';
	}

	function addParticipant() {
		const id = participantInput.trim();
		if (id && !draft.participantIds.includes(id)) draft.participantIds = [...draft.participantIds, id];
		participantInput = '';
	}

	function removeParticipant(id: string) {
		draft.participantIds = draft.participantIds.filter((participant) => participant !== id);
	}

	function save() {
		const result = onSave?.({ ...draft, id: selectedId ?? draft.id });
		if (!result) return;
		if (!result.ok) {
			errors = result.errors;
			return;
		}
		selectedId = result.event.id;
		draft = eventToDraft(result.event);
		errors = [];
	}

	function remove() {
		if (selectedId) onDelete?.(selectedId);
		startNew();
	}
</script>

<div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
	<Card>
		<CardHeader class="flex-row items-center justify-between">
			<div><CardTitle class="text-base">Historické události</CardTitle><p class="mt-1 text-xs text-muted-foreground">Intervalová historie světa, oddělená od mapy a rodokmenu.</p></div>
			<Button size="sm" onclick={startNew}><Plus class="mr-1 h-3.5 w-3.5" />Nová událost</Button>
		</CardHeader>
		<CardContent>
			{#if orderedEvents.length === 0}
				<div class="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">Zatím nejsou zaznamenané žádné události.</div>
			{:else}
				<div class="space-y-2">
					{#each orderedEvents as event (event.id)}
						<button class="flex w-full items-start justify-between rounded-lg border p-3 text-left transition hover:bg-muted {selectedId === event.id ? 'border-primary bg-muted/50' : ''}" onclick={() => selectEvent(event)}>
							<span class="min-w-0"><span class="flex items-center gap-2 text-sm font-medium"><CalendarPlus class="h-4 w-4 shrink-0 text-muted-foreground" />{event.title}</span><span class="mt-1 block text-xs text-muted-foreground">{HISTORICAL_EVENT_LABELS[event.kind]} · {event.interval.startYear}{event.interval.endYear === null ? '–' : `–${event.interval.endYear}`} · {eventParticipants(event, languages)}</span></span>
							<Pencil class="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
						</button>
					{/each}
				</div>
			{/if}
		</CardContent>
	</Card>

	<Card>
		<CardHeader><CardTitle class="text-base">{selectedId ? 'Upravit událost' : 'Nová událost'}</CardTitle></CardHeader>
		<CardContent class="space-y-4">
			<div class="grid grid-cols-2 gap-3">
				<label class="space-y-1 text-xs"><span class="text-muted-foreground">Typ</span><select class="h-8 w-full rounded-lg border bg-background px-2" bind:value={draft.kind}>{#each HISTORICAL_EVENT_KINDS as kind}<option value={kind}>{HISTORICAL_EVENT_LABELS[kind]}</option>{/each}</select></label>
				<label class="space-y-1 text-xs"><span class="text-muted-foreground">Název</span><input class="h-8 w-full rounded-lg border bg-background px-2" placeholder="Např. Velká migrace" bind:value={draft.title} /></label>
			</div>
			<div class="grid grid-cols-2 gap-3">
				<label class="space-y-1 text-xs"><span class="text-muted-foreground">Začátek</span><input class="h-8 w-full rounded-lg border bg-background px-2" type="number" bind:value={draft.startYear} /></label>
				<label class="space-y-1 text-xs"><span class="text-muted-foreground">Konec (volitelný)</span><input class="h-8 w-full rounded-lg border bg-background px-2" type="number" placeholder="probíhá" bind:value={draft.endYear} /></label>
			</div>
			<div class="space-y-2"><div class="text-xs text-muted-foreground">Účastníci</div><div class="flex gap-2"><input class="h-8 min-w-0 flex-1 rounded-lg border bg-background px-2 text-sm" placeholder="ID jazyka" bind:value={participantInput} onkeydown={(event) => event.key === 'Enter' && addParticipant()} /><Button size="sm" variant="outline" onclick={addParticipant}>Přidat</Button></div>{#if draft.participantIds.length}<div class="flex flex-wrap gap-1.5">{#each draft.participantIds as id}<button class="rounded-full bg-muted px-2 py-1 text-xs hover:bg-destructive/10" title="Odebrat účastníka" onclick={() => removeParticipant(id)}>{languageNames.get(id) ?? id} ×</button>{/each}</div>{/if}</div>
			{#if errors.length}<div class="rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive"><ul class="list-disc space-y-1 pl-4">{#each errors as error}<li>{error}</li>{/each}</ul></div>{/if}
			<div class="flex justify-between gap-2 border-t pt-3"><div>{#if selectedId}<Button size="sm" variant="destructive" onclick={remove}><Trash2 class="mr-1 h-3.5 w-3.5" />Smazat</Button>{/if}</div><Button size="sm" onclick={save}>Uložit událost</Button></div>
		</CardContent>
	</Card>
</div>

<Card class="mt-4 border-dashed">
	<CardContent class="pt-5 text-xs leading-relaxed text-muted-foreground"><strong class="text-foreground">Kontrakt timeline:</strong> Událost má interval, účastníky a účinek v čase. Úprava zde nemění mapovou geometrii ani genealogické vztahy; migrace, válka a kontakt je ovlivní až při explicitním zpracování simulací.</CardContent>
</Card>
