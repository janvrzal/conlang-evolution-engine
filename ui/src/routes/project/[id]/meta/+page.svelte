<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';

	import { ipaManners, ipaPlaces, ipaConsonants, ipaVowelsFrontness, ipaVowelsOpenness, ipaVowels, languagePresets, type LanguagePreset } from '$lib/data/languagePresets';
	import { generateProtolangApi, resetApiBase } from '$lib/api';
	import { projectState } from '$lib/state.svelte';

	// State
	let protoLanguages = $state<{ id: string; name: string; presetId: string; consonants: Set<string>; vowels: Set<string>; syllable: string }[]>([
		{ id: 'proto-1', name: 'Proto-Jazyk 1', presetId: 'empty', consonants: new Set(), vowels: new Set(), syllable: '(C)V' }
	]);
	let activeProtoId = $state('proto-1');
	
	let activeProto = $derived(protoLanguages.find(p => p.id === activeProtoId)!);

	// Time steps state
	let timeSteps = $state([
		{ year: 0, description: 'Základní protojazyk' }
	]);
	
	let newYear = $state('');
	let newDesc = $state('');

	function addProtoLanguage() {
		const newId = `proto-${Date.now()}`;
		protoLanguages = [...protoLanguages, { id: newId, name: `Nový Proto-Jazyk`, presetId: 'empty', consonants: new Set(), vowels: new Set(), syllable: '(C)V' }];
		activeProtoId = newId;
	}

	function removeProtoLanguage(id: string) {
		if (protoLanguages.length <= 1) return;
		protoLanguages = protoLanguages.filter(p => p.id !== id);
		if (activeProtoId === id) activeProtoId = protoLanguages[0].id;
	}

	function handlePresetChange(e: Event) {
		const select = e.target as HTMLSelectElement;
		const presetId = select.value;
		const preset = languagePresets.find(p => p.id === presetId);
		if (!preset) return;

		protoLanguages = protoLanguages.map(p => {
			if (p.id === activeProtoId) {
				return {
					...p,
					presetId,
					consonants: new Set(preset.consonants),
					vowels: new Set(preset.vowels),
					syllable: preset.syllable
				};
			}
			return p;
		});
	}

	function toggleConsonant(symbol: string) {
		const newSet = new Set(activeProto.consonants);
		if (newSet.has(symbol)) {
			newSet.delete(symbol);
		} else {
			newSet.add(symbol);
		}
		
		protoLanguages = protoLanguages.map(p => p.id === activeProtoId ? { ...p, consonants: newSet, presetId: 'empty' } : p);
	}

	function toggleVowel(symbol: string) {
		const newSet = new Set(activeProto.vowels);
		if (newSet.has(symbol)) {
			newSet.delete(symbol);
		} else {
			newSet.add(symbol);
		}
		
		protoLanguages = protoLanguages.map(p => p.id === activeProtoId ? { ...p, vowels: newSet, presetId: 'empty' } : p);
	}
	
	function addTimeStep(e: Event) {
		e.preventDefault();
		if (!newYear) return;
		timeSteps = [...timeSteps, { year: Number(newYear), description: newDesc }].sort((a, b) => a.year - b.year);
		newYear = '';
		newDesc = '';
	}
	
	function removeTimeStep(index: number) {
		timeSteps = timeSteps.filter((_, i) => i !== index);
	}

	function proceedToMap() {
		goto(`/project/${$page.params.id}/map`);
	}

	let isGenerating = $state(false);
	let generateError = $state('');

	async function generateLexicon() {
		if (activeProto.consonants.size === 0 || activeProto.vowels.size === 0) {
			generateError = 'Je potřeba vybrat alespoň jednu souhlásku a samohlásku.';
			return;
		}

		isGenerating = true;
		generateError = '';
		try {
			const cons = Array.from(activeProto.consonants).join(' ');
			const vows = Array.from(activeProto.vowels).join(' ');
			
			const data = await generateProtolangApi({
				consonants: cons,
				vowels: vows,
				syllable_structure: activeProto.syllable
			});
			
			if (data.status === 'success') {
				projectState.generatedProtoLexicon = data.words;
			} else {
				generateError = `Generátor vrátil chybový stav '${data.status}'.`;
			}
		} catch (e) {
			resetApiBase();
			generateError = e instanceof Error ? e.message : String(e);
		} finally {
			isGenerating = false;
		}
	}
</script>

<svelte:head>
	<title>Metaeditace | Projekt {$page.params.id}</title>
</svelte:head>

<div class="min-h-screen bg-background flex flex-col p-6 max-w-7xl mx-auto gap-8">
	<header class="flex items-center justify-between border-b pb-4">
		<div>
			<h1 class="text-3xl font-bold tracking-tight">Metaeditace: {$page.params.id}</h1>
			<p class="text-muted-foreground">Příprava protojazyků a časové osy.</p>
		</div>
		<Button variant="outline" onclick={() => goto('/')}>Zpět do menu</Button>
	</header>

	<div class="grid lg:grid-cols-4 gap-6 items-start">
		<!-- Sidebar for multiple proto languages -->
		<aside class="lg:col-span-1 space-y-4">
			<Card>
				<CardHeader class="pb-3">
					<CardTitle>Proto-Jazyky</CardTitle>
				</CardHeader>
				<CardContent class="space-y-2">
					{#each protoLanguages as lang}
						<div role="button" tabindex="0" class="flex items-center justify-between gap-2 p-2 border rounded-md cursor-pointer {activeProtoId === lang.id ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-muted'}" onclick={() => activeProtoId = lang.id} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activeProtoId = lang.id; } }}>
							<span class="font-medium text-sm truncate">{lang.name}</span>
							{#if protoLanguages.length > 1}
								<button class="text-xs opacity-50 hover:opacity-100" onclick={(e) => { e.stopPropagation(); removeProtoLanguage(lang.id); }}>✕</button>
							{/if}
						</div>
					{/each}
					<Button variant="outline" class="w-full mt-2" onclick={addProtoLanguage}>+ Přidat další</Button>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="pb-3">
					<CardTitle>Časová osa</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					<form onsubmit={addTimeStep} class="space-y-2">
						<div class="flex gap-2">
							<Input type="number" bind:value={newYear} placeholder="Rok" class="w-20" />
							<Input bind:value={newDesc} placeholder="Milník" />
						</div>
						<Button type="submit" class="w-full" size="sm">Přidat</Button>
					</form>
					<div class="space-y-2 max-h-60 overflow-y-auto">
						{#each timeSteps as step, i}
							<div class="flex items-center justify-between text-sm border-b pb-1">
								<span><strong class="w-10 inline-block">{step.year}</strong> {step.description}</span>
								{#if i > 0}
									<button class="text-destructive text-xs" onclick={() => removeTimeStep(i)}>✕</button>
								{/if}
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>
		</aside>

		<!-- Main Editor for active proto language -->
		<main class="lg:col-span-3 space-y-6">
			<Card>
				<CardHeader class="pb-3 border-b mb-4 flex flex-row items-center justify-between">
					<div>
						<Input value={activeProto.name} oninput={(e: Event & { currentTarget: HTMLInputElement }) => {
							protoLanguages = protoLanguages.map(p => p.id === activeProtoId ? { ...p, name: e.currentTarget.value } : p);
						}} class="text-xl font-bold h-auto border-transparent hover:border-input focus:border-input focus-visible:ring-0 px-0 -ml-2" />
						<CardDescription>Definujte fonetický inventář a strukturu slabiky vybraného jazyka.</CardDescription>
					</div>
					
					<div class="flex items-center gap-2">
						<Label for="preset">Předvolba:</Label>
						<select id="preset" class="border rounded px-3 py-1.5 text-sm bg-background" value={activeProto.presetId} onchange={handlePresetChange}>
							{#each languagePresets as preset}
								<option value={preset.id}>{preset.name}</option>
							{/each}
						</select>
					</div>
				</CardHeader>

				<CardContent class="space-y-8">
					<div class="space-y-4">
						<h3 class="font-semibold border-b pb-1">IPA Souhlásky (Consonants)</h3>
						<div class="overflow-x-auto pb-4">
							<table class="w-full text-sm border-collapse">
								<thead>
									<tr>
										<th class="border p-2 text-left bg-muted/30">Způsob \ Místo</th>
										{#each ipaPlaces as place}
											<th class="border p-1 text-center font-normal text-xs bg-muted/10">{place}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each ipaManners as manner}
										<tr>
											<th class="border p-2 text-left font-normal bg-muted/10">{manner}</th>
											{#each ipaPlaces as place}
												<td class="border p-1 text-center min-w-[3.5rem]">
													{#if ipaConsonants[manner] && ipaConsonants[manner][place]}
														<div class="flex justify-center gap-1">
															{#each ipaConsonants[manner][place] as symbol, i}
																{#if symbol}
																	<!-- svelte-ignore a11y_click_events_have_key_events -->
																	<!-- svelte-ignore a11y_no_static_element_interactions -->
																	<span 
																		class="inline-block w-5 h-5 text-center leading-5 rounded cursor-pointer select-none transition-colors {activeProto.consonants.has(symbol) ? 'bg-primary text-primary-foreground font-bold' : 'hover:bg-muted'}"
																		onclick={() => toggleConsonant(symbol)}
																	>
																		{symbol}
																	</span>
																{:else}
																	<span class="w-5 h-5"></span>
																{/if}
															{/each}
														</div>
													{/if}
												</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
					</div>

					<div class="grid md:grid-cols-2 gap-8">
						<div class="space-y-4">
							<h3 class="font-semibold border-b pb-1">IPA Samohlásky (Vowels)</h3>
							<table class="w-full text-sm border-collapse">
								<thead>
									<tr>
										<th class="border p-1 text-left bg-muted/30">Otevřenost \ Poloha</th>
										{#each ipaVowelsFrontness as frontness}
											<th class="border p-1 text-center font-normal bg-muted/10">{frontness}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each ipaVowelsOpenness as openness}
										<tr>
											<th class="border p-1 text-left font-normal bg-muted/10 text-xs">{openness}</th>
											{#each ipaVowelsFrontness as frontness}
												<td class="border p-1 text-center">
													{#if ipaVowels[openness] && ipaVowels[openness][frontness]}
														<div class="flex justify-center gap-1">
															{#each ipaVowels[openness][frontness] as symbol}
																{#if symbol}
																	<!-- svelte-ignore a11y_click_events_have_key_events -->
																	<!-- svelte-ignore a11y_no_static_element_interactions -->
																	<span 
																		class="inline-block w-5 h-5 text-center leading-5 rounded cursor-pointer select-none transition-colors {activeProto.vowels.has(symbol) ? 'bg-primary text-primary-foreground font-bold' : 'hover:bg-muted'}"
																		onclick={() => toggleVowel(symbol)}
																	>
																		{symbol}
																	</span>
																{:else}
																	<span class="w-5 h-5"></span>
																{/if}
															{/each}
														</div>
													{/if}
												</td>
											{/each}
										</tr>
									{/each}
								</tbody>
							</table>
						</div>
						
						<div class="space-y-4">
							<h3 class="font-semibold border-b pb-1">Struktura slabiky & Slova</h3>
							<div class="space-y-4">
								<div class="space-y-2">
									<Label for="syllable">Vzorec slabiky (C=Souhláska, V=Samohláska, závorky=volitelné)</Label>
									<!-- Use value binding instead of two-way bind for derived objects because we mutate via helper -->
									<Input id="syllable" value={activeProto.syllable} oninput={(e: Event & { currentTarget: HTMLInputElement }) => {
										protoLanguages = protoLanguages.map(p => p.id === activeProtoId ? { ...p, syllable: e.currentTarget.value, presetId: 'empty' } : p);
									}} class="font-mono" />
								</div>
								
								<div class="p-4 bg-muted/30 rounded-md border text-sm text-muted-foreground">
									<p>Aktivní souhlásky: <strong class="text-foreground">{Array.from(activeProto.consonants).join(', ') || 'Žádné'}</strong></p>
									<p class="mt-2">Aktivní samohlásky: <strong class="text-foreground">{Array.from(activeProto.vowels).join(', ') || 'Žádné'}</strong></p>
								</div>
								
								<Button variant="secondary" class="w-full" onclick={generateLexicon} disabled={isGenerating}>
									{isGenerating ? 'Generuji...' : 'Vygenerovat testovací slovník'}
								</Button>
								
								{#if generateError}
									<p class="text-destructive text-sm font-medium">{generateError}</p>
								{/if}
								
								{#if projectState.generatedProtoLexicon.length > 0}
									<p class="text-green-600 text-sm font-medium">Úspěšně vygenerováno {projectState.generatedProtoLexicon.length} slov.</p>
								{/if}
							</div>
						</div>
					</div>
				</CardContent>
			</Card>
		</main>
	</div>

	<footer class="flex justify-end pt-4 mt-auto">
		<Button size="lg" onclick={proceedToMap}>Uložit a pokračovat na Fyzickou mapu</Button>
	</footer>
</div>
