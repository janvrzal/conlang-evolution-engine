<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Loader2, Trash2 } from 'lucide-svelte';

	import { deleteProject, listProjects, saveProject, slugify } from '$lib/api';

	type Summary = { id: string; name: string; updated_at: string | null };

	// Seznam se načítá z backendu. Dřív tu byla natvrdo vymyšlená dvojice
	// projektů, takže skutečně uložené projekty nešlo znovu najít.
	let projects = $state<Summary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let newProjectName = $state('');
	let creating = $state(false);

	let newId = $derived(slugify(newProjectName));
	let conflict = $derived(newId !== '' && projects.some((p) => p.id === newId));

	onMount(refresh);

	async function refresh() {
		loading = true;
		error = null;
		try {
			projects = await listProjects();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	async function createNewProject(e: Event) {
		e.preventDefault();
		if (!newId || creating) return;

		creating = true;
		error = null;
		try {
			// Projekt zakládáme hned na backendu, ať existuje i v seznamu —
			// ne až ho něco uloží mimochodem.
			await saveProject(newId, { name: newProjectName.trim(), data: {} });
			await goto(`/project/${encodeURIComponent(newId)}/meta`);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			creating = false;
		}
	}

	async function remove(project: Summary, event: MouseEvent) {
		event.stopPropagation();
		if (!confirm(`Opravdu smazat projekt „${displayName(project)}"? Tohle nejde vrátit.`)) return;

		try {
			await deleteProject(project.id);
			projects = projects.filter((p) => p.id !== project.id);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	function openProject(id: string) {
		goto(`/project/${encodeURIComponent(id)}/map`);
	}

	/**
	 * Projekty založené starším postupem mají generické jméno „Nový projekt".
	 * Jejich ID přitom nese to, co uživatel skutečně napsal, tak ukážeme to.
	 */
	function displayName(project: Summary): string {
		const name = project.name?.trim();
		return !name || name === 'Nový projekt' ? project.id : name;
	}

	function formatDate(iso: string | null): string {
		if (!iso) return 'neznámo kdy';
		const d = new Date(iso);
		return Number.isNaN(d.getTime())
			? iso
			: d.toLocaleString('cs-CZ', { dateStyle: 'medium', timeStyle: 'short' });
	}
</script>

<svelte:head>
	<title>CEE | Conlang Evolution Engine</title>
</svelte:head>

<div class="min-h-screen bg-background flex flex-col items-center justify-center p-4">
	<div class="w-full max-w-4xl grid md:grid-cols-2 gap-8">
		<section class="flex flex-col gap-4">
			<div class="space-y-2 mb-4">
				<h1 class="text-4xl font-bold tracking-tight">Conlang Evolution Engine</h1>
				<p class="text-muted-foreground">Vytvořte a simulujte evoluci nového jazyka.</p>
			</div>

			<Card>
				<CardHeader>
					<CardTitle>Nový projekt</CardTitle>
					<CardDescription>Zadejte název pro novou simulaci.</CardDescription>
				</CardHeader>
				<form onsubmit={createNewProject}>
					<CardContent>
						<div class="grid w-full items-center gap-4">
							<div class="flex flex-col space-y-1.5">
								<Label for="name">Název projektu</Label>
								<Input id="name" placeholder="Např. Pragermánština" bind:value={newProjectName} />
								{#if newId}
									<p class="text-xs text-muted-foreground">
										Adresa projektu: <code>/project/{newId}</code>
									</p>
								{/if}
								{#if conflict}
									<p class="text-xs text-destructive">
										Projekt s tímto názvem už existuje — otevřete ho vpravo, nebo zvolte jiný název.
									</p>
								{/if}
							</div>
						</div>
					</CardContent>
					<CardFooter class="flex-col items-stretch gap-2">
						<Button type="submit" class="w-full" disabled={!newId || conflict || creating}>
							{creating ? 'Zakládám…' : 'Vytvořit projekt'}
						</Button>
						{#if error}
							<p class="text-xs text-destructive">{error}</p>
						{/if}
					</CardFooter>
				</form>
			</Card>
		</section>

		<section class="flex flex-col gap-4">
			<div class="space-y-2 mb-4">
				<h2 class="text-2xl font-semibold tracking-tight mt-10 md:mt-0">Otevřít existující</h2>
				<p class="text-muted-foreground">Pokračujte v práci na rozpracovaných projektech.</p>
			</div>

			<div class="grid gap-3">
				{#if loading}
					<div class="flex items-center gap-2 text-sm text-muted-foreground p-8 justify-center">
						<Loader2 class="w-4 h-4 animate-spin" /> Načítám projekty…
					</div>
				{:else if error && projects.length === 0}
					<div class="text-sm border border-dashed rounded-lg p-6 space-y-3">
						<p class="text-destructive">{error}</p>
						<Button variant="outline" size="sm" onclick={refresh}>Zkusit znovu</Button>
					</div>
				{:else}
					{#each projects as project (project.id)}
						<Card
							class="hover:bg-muted/50 cursor-pointer transition-colors"
							onclick={() => openProject(project.id)}
						>
							<CardHeader class="pb-3">
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0">
										<CardTitle class="text-lg truncate">{displayName(project)}</CardTitle>
										<CardDescription>
											Naposledy upraveno: {formatDate(project.updated_at)}
										</CardDescription>
									</div>
									<Button
										variant="ghost"
										size="sm"
										class="h-8 w-8 p-0 shrink-0 text-muted-foreground hover:text-destructive"
										title="Smazat projekt"
										onclick={(e) => remove(project, e)}
									>
										<Trash2 class="w-4 h-4" />
									</Button>
								</div>
							</CardHeader>
						</Card>
					{:else}
						<div
							class="text-sm text-muted-foreground border border-dashed rounded-lg p-8 text-center"
						>
							Zatím nemáte žádné projekty.
						</div>
					{/each}
				{/if}
			</div>
		</section>
	</div>
</div>
