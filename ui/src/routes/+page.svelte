<script lang="ts">
	import { goto } from '$app/navigation';
	import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';

	// Mocked existing projects for demonstration
	let existingProjects = [
		{ id: 'latina-1', name: 'Vývoj Latiny', lastModified: '2026-08-27' },
		{ id: 'fantasy-elf', name: 'Elfský jazyk (Fantasy)', lastModified: '2026-08-25' }
	];

	let newProjectName = $state('');

	function createNewProject(e: Event) {
		e.preventDefault();
		if (!newProjectName.trim()) return;
		
		const newId = newProjectName.trim().toLowerCase().replace(/\s+/g, '-');
		// Redirect to meta editor
		goto(`/project/${newId}/meta`);
	}

	function openProject(id: string) {
		// Can go straight to map, but typically you might go to meta or dashboard
		goto(`/project/${id}/map`);
	}
</script>

<svelte:head>
	<title>CEE | Conlang Evolution Engine</title>
</svelte:head>

<div class="min-h-screen bg-background flex flex-col items-center justify-center p-4">
	<div class="w-full max-w-4xl grid md:grid-cols-2 gap-8">
		
		<!-- Založit nový projekt -->
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
							</div>
						</div>
					</CardContent>
					<CardFooter>
						<Button type="submit" class="w-full" disabled={!newProjectName.trim()}>
							Vytvořit projekt
						</Button>
					</CardFooter>
				</form>
			</Card>
		</section>

		<!-- Existující projekty -->
		<section class="flex flex-col gap-4">
			<div class="space-y-2 mb-4">
				<h2 class="text-2xl font-semibold tracking-tight mt-10 md:mt-0">Otevřít existující</h2>
				<p class="text-muted-foreground">Pokračujte v práci na rozpracovaných projektech.</p>
			</div>
			
			<div class="grid gap-3">
				{#each existingProjects as project}
					<Card class="hover:bg-muted/50 cursor-pointer transition-colors" onclick={() => openProject(project.id)}>
						<CardHeader class="pb-3">
							<CardTitle class="text-lg">{project.name}</CardTitle>
							<CardDescription>Naposledy upraveno: {project.lastModified}</CardDescription>
						</CardHeader>
					</Card>
				{/each}
				
				{#if existingProjects.length === 0}
					<div class="text-sm text-muted-foreground border border-dashed rounded-lg p-8 text-center">
						Zatím nemáte žádné projekty.
					</div>
				{/if}
			</div>
		</section>

	</div>
</div>
