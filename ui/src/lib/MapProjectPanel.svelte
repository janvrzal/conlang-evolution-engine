<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Download } from 'lucide-svelte';
	import { projectState } from '$lib/state.svelte';
	import { t } from '$lib/i18n.svelte';
	import { scheduleSave } from '$lib/state.svelte';

	let backgroundError = $state('');
	function addPolity() {
		projectState.polities = [
			...projectState.polities,
			{
				id: `state-${Date.now()}`,
				name: 'Nový stát',
				territory: [],
				institutions: { internal_contact: 0.35, standardization: 0.3 },
				languageIds: []
			}
		];
		scheduleSave();
	}
	function addRoute() {
		projectState.tradeRoutes = [
			...projectState.tradeRoutes,
			{
				id: `route-${Date.now()}`,
				kind: 'land',
				intensity: 0.5,
				languageIds: [],
				startYear: currentYear,
				endYear: null,
				waypoints: []
			}
		];
		scheduleSave();
	}
	function addHistoricalEvent() {
		projectState.historicalEvents = [
			...projectState.historicalEvents,
			{
				id: `event-${Date.now()}`,
				kind: 'migration',
				startYear: currentYear,
				duration: 0,
				targetLanguageIds: [],
				endonym: '',
				exonym: '',
				effects: {}
			}
		];
		scheduleSave();
	}
	function removeItem(key: 'polities' | 'tradeRoutes' | 'historicalEvents', id: string) {
		projectState[key] = projectState[key].filter((item: any) => item.id !== id);
		scheduleSave();
	}
	const MAX_BACKGROUND_BYTES = 5 * 1024 * 1024;

	function readFile(file: File): Promise<string> {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onerror = () => reject(reader.error);
			reader.onload = () => resolve(String(reader.result));
			reader.readAsDataURL(file);
		});
	}

	async function importBackground(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		if (!file.type.startsWith('image/')) {
			backgroundError = 'Vyber obrázek ve formátu PNG, JPEG, WebP nebo SVG.';
			return;
		}
		if (file.size > MAX_BACKGROUND_BYTES) {
			backgroundError = 'Podklad může mít nejvýše 5 MB.';
			return;
		}
		try {
			projectState.mapBackground = { dataUrl: await readFile(file), scale: 100, opacity: 0.35 };
			backgroundError = '';
			scheduleSave();
		} catch {
			backgroundError = 'Obrázek se nepodařilo načíst.';
		}
	}

	let {
		currentYear,
		drawingRouteId = null,
		onDrawRoute,
		isLoading,
		errorMessage = '',
		onAddLanguage,
		onRunSimulation,
		onExport,
		onImportLegacy
	}: {
		currentYear: number;
		drawingRouteId?: string | null;
		onDrawRoute: (routeId: string) => void;
		isLoading: boolean;
		errorMessage?: string;
		onAddLanguage: () => void;
		onRunSimulation: () => void;
		onExport: () => void;
		onImportLegacy: () => void;
	} = $props();
</script>

<Card class="shadow-sm">
	<CardHeader class="pb-3"
		><CardTitle class="text-lg">Projekt: {projectState.name}</CardTitle></CardHeader
	>
	<CardContent class="space-y-4">
		<Button class="w-full" variant="outline" size="sm" onclick={onAddLanguage}
			>+ {t('addNode')}</Button
		>
		<Button
			class="w-full"
			variant="outline"
			size="sm"
			onclick={() => goto(`/project/${$page.params.id}/meta`)}>{t('projectSettings')}</Button
		>
		<Button
			class="w-full relative overflow-hidden"
			variant="default"
			size="sm"
			onclick={onRunSimulation}
			disabled={isLoading}
		>
			<span class="relative z-10">{isLoading ? '…' : t('simulate')}</span>
			{#if isLoading}<div
					class="absolute bottom-0 left-0 h-1 bg-white/40 animate-pulse transition-all duration-[800ms] ease-out w-full"
					style="animation: fillProgress 800ms ease-out forwards;"
				></div>{/if}
		</Button>
		{#if projectState.simulationRunId}
			<Button class="w-full" variant="outline" size="sm" onclick={onExport}
				><Download class="w-4 h-4 mr-2" /> Exportovat simulaci</Button
			>
		{:else}
			<Button
				class="w-full"
				variant="outline"
				size="sm"
				onclick={onImportLegacy}
				disabled={isLoading}>{t('importLegacy')}</Button
			>
		{/if}
		{#if errorMessage}<p class="text-xs text-destructive">{errorMessage}</p>{/if}
		<div class="space-y-2 border-t pt-3">
			<div class="flex items-center justify-between">
				<p class="text-xs font-medium">Státy, trasy a události</p>
				<div class="flex gap-1">
					<Button size="xs" variant="outline" onclick={addPolity}>Stát</Button><Button
						size="xs"
						variant="outline"
						onclick={addRoute}>Trasa</Button
					><Button size="xs" variant="outline" onclick={addHistoricalEvent}>Událost</Button>
				</div>
			</div>
			{#each projectState.polities as polity, index (polity.id)}<div
					class="rounded border p-2 text-xs space-y-2"
				>
					<div class="flex gap-1">
						<Input
							value={polity.name}
							aria-label="Název státu"
							oninput={(e) => {
								projectState.polities[index] = { ...polity, name: e.currentTarget.value };
								scheduleSave();
							}}
						/><Button size="xs" variant="ghost" onclick={() => removeItem('polities', polity.id)}
							>×</Button
						>
					</div>
					<Input
						placeholder="ID jazyků, čárkou"
						value={(polity.languageIds ?? []).join(',')}
						oninput={(e) => {
							projectState.polities[index] = {
								...polity,
								languageIds: e.currentTarget.value
									.split(',')
									.map((v) => v.trim())
									.filter(Boolean)
							};
							scheduleSave();
						}}
					/><label
						>Vnitřní kontakt {Math.round(
							Number(polity.institutions?.internal_contact ?? 0.35) * 100
						)}%<Input
							type="range"
							min="0"
							max="1"
							step=".05"
							value={Number(polity.institutions?.internal_contact ?? 0.35)}
							oninput={(e) => {
								projectState.polities[index] = {
									...polity,
									institutions: {
										...(polity.institutions ?? {}),
										internal_contact: Number(e.currentTarget.value)
									}
								};
								scheduleSave();
							}}
						/></label
					><label
						>Standardizace {Math.round(
							Number(polity.institutions?.standardization ?? 0.3) * 100
						)}%<Input
							type="range"
							min="0"
							max="1"
							step=".05"
							value={Number(polity.institutions?.standardization ?? 0.3)}
							oninput={(e) => {
								projectState.polities[index] = {
									...polity,
									institutions: {
										...(polity.institutions ?? {}),
										standardization: Number(e.currentTarget.value)
									}
								};
								scheduleSave();
							}}
						/></label
					>
				</div>{/each}
			{#each projectState.tradeRoutes as route, index (route.id)}<div
					class="rounded border p-2 text-xs grid gap-2"
				>
					<div class="flex gap-1">
						<select
							class="flex-1"
							value={route.kind}
							onchange={(e) => {
								projectState.tradeRoutes[index] = { ...route, kind: e.currentTarget.value };
								scheduleSave();
							}}
							><option value="land">pozemní</option><option value="sea">námořní</option><option
								value="river">říční</option
							></select
						><Button
							size="xs"
							variant={drawingRouteId === route.id ? 'default' : 'outline'}
							onclick={() => onDrawRoute(route.id)}
							>{drawingRouteId === route.id ? 'Hotovo' : 'Kreslit'}</Button
						><Button size="xs" variant="ghost" onclick={() => removeItem('tradeRoutes', route.id)}
							>×</Button
						>
					</div>
					<Input
						placeholder="ID jazyků v pořadí, čárkou"
						value={(route.languageIds ?? []).join(',')}
						oninput={(e) => {
							projectState.tradeRoutes[index] = {
								...route,
								languageIds: e.currentTarget.value
									.split(',')
									.map((v) => v.trim())
									.filter(Boolean)
							};
							scheduleSave();
						}}
					/>
					<div class="grid grid-cols-2 gap-1">
						<Input
							aria-label="Rok začátku"
							type="number"
							value={route.startYear}
							oninput={(e) => {
								projectState.tradeRoutes[index] = {
									...route,
									startYear: Number(e.currentTarget.value)
								};
								scheduleSave();
							}}
						/><Input
							aria-label="Rok konce"
							type="number"
							placeholder="konec"
							value={route.endYear ?? ''}
							oninput={(e) => {
								projectState.tradeRoutes[index] = {
									...route,
									endYear: e.currentTarget.value ? Number(e.currentTarget.value) : null
								};
								scheduleSave();
							}}
						/>
					</div>
					<label
						>Intenzita {Math.round(Number(route.intensity ?? 0.5) * 100)}%<Input
							type="range"
							min="0"
							max="1"
							step=".05"
							value={Number(route.intensity ?? 0.5)}
							oninput={(e) => {
								projectState.tradeRoutes[index] = {
									...route,
									intensity: Number(e.currentTarget.value)
								};
								scheduleSave();
							}}
						/></label
					>
					<div class="flex items-center justify-between text-muted-foreground">
						<span>{(route.waypoints ?? []).length} bodů na mapě</span><Button
							size="xs"
							variant="ghost"
							onclick={() => {
								projectState.tradeRoutes[index] = { ...route, waypoints: [] };
								scheduleSave();
							}}>Vyčistit trasu</Button
						>
					</div>
				</div>{/each}
			{#each projectState.historicalEvents as event, index (event.id)}<div
					class="rounded border p-2 text-xs grid gap-2"
				>
					<div class="flex gap-1">
						<select
							class="flex-1"
							value={event.kind}
							onchange={(e) => {
								projectState.historicalEvents[index] = { ...event, kind: e.currentTarget.value };
								scheduleSave();
							}}
							><option value="migration">migrace</option><option value="war">válka</option><option
								value="collapse">kolaps</option
							><option value="urbanization">urbanizace</option><option value="standardization"
								>standardizace</option
							><option value="religious_reform">náboženská reforma</option><option
								value="trade_boom">obchodní rozkvět</option
							><option value="rename">politické přejmenování</option></select
						><Button
							size="xs"
							variant="ghost"
							onclick={() => removeItem('historicalEvents', event.id)}>×</Button
						>
					</div>
					<div class="grid grid-cols-2 gap-1">
						<Input
							aria-label="Rok"
							type="number"
							value={event.startYear}
							oninput={(e) => {
								projectState.historicalEvents[index] = {
									...event,
									startYear: Number(e.currentTarget.value)
								};
								scheduleSave();
							}}
						/><Input
							aria-label="Trvání"
							type="number"
							placeholder="trvání"
							value={event.duration ?? 0}
							oninput={(e) => {
								projectState.historicalEvents[index] = {
									...event,
									duration: Number(e.currentTarget.value)
								};
								scheduleSave();
							}}
						/>
					</div>
					<Input
						placeholder="Cílové jazyky, čárkou (nebo nechat prázdné)"
						value={(event.targetLanguageIds ?? []).join(',')}
						oninput={(e) => {
							projectState.historicalEvents[index] = {
								...event,
								targetLanguageIds: e.currentTarget.value
									.split(',')
									.map((v) => v.trim())
									.filter(Boolean)
							};
							scheduleSave();
						}}
					/>{#if event.kind === 'rename'}<Input
							placeholder="Nové endonymum"
							value={event.endonym ?? ''}
							oninput={(e) => {
								projectState.historicalEvents[index] = { ...event, endonym: e.currentTarget.value };
								scheduleSave();
							}}
						/><Input
							placeholder="Nové exonymum"
							value={event.exonym ?? ''}
							oninput={(e) => {
								projectState.historicalEvents[index] = { ...event, exonym: e.currentTarget.value };
								scheduleSave();
							}}
						/>{/if}
				</div>{/each}
		</div>
		<div class="space-y-2 border-t pt-3">
			<p class="text-xs font-medium">Podklad mapy</p>
			<Input
				type="file"
				accept="image/png,image/jpeg,image/webp,image/svg+xml"
				onchange={importBackground}
			/>
			{#if projectState.mapBackground}
				<label class="block text-xs text-muted-foreground"
					>Měřítko: {Math.round(projectState.mapBackground.scale)}%
					<Input
						type="range"
						min="25"
						max="300"
						step="5"
						bind:value={projectState.mapBackground.scale}
						oninput={scheduleSave}
					/>
				</label>
				<label class="block text-xs text-muted-foreground"
					>Viditelnost: {Math.round(projectState.mapBackground.opacity * 100)}%
					<Input
						type="range"
						min="0.05"
						max="0.9"
						step="0.05"
						bind:value={projectState.mapBackground.opacity}
						oninput={scheduleSave}
					/>
				</label>
				<Button
					variant="ghost"
					size="sm"
					class="w-full text-destructive hover:text-destructive"
					onclick={() => {
						projectState.mapBackground = null;
						scheduleSave();
					}}>Odebrat podklad</Button
				>
			{/if}
			{#if backgroundError}<p class="text-xs text-destructive">{backgroundError}</p>{/if}
		</div>
		<div class="text-xs text-muted-foreground space-y-1">
			<p>{t('currentStep')}: <strong>{t('year')} {currentYear}</strong></p>
			<p class="flex items-center gap-1.5">
				{#if projectState.status === 'saving'}<span class="w-1.5 h-1.5 rounded-full bg-amber-500"
					></span> Ukládám…
				{:else if projectState.status === 'dirty'}<span
						class="w-1.5 h-1.5 rounded-full bg-amber-500"
					></span> Neuloženo
				{:else if projectState.status === 'error'}<span
						class="w-1.5 h-1.5 rounded-full bg-destructive"
					></span><span class="text-destructive">Uložení selhalo</span>
				{:else if projectState.status === 'saved'}<span
						class="w-1.5 h-1.5 rounded-full bg-emerald-500"
					></span>
					{t('saved')}{/if}
			</p>
			{#if projectState.error}<p class="text-destructive">{projectState.error}</p>{/if}
		</div>
	</CardContent>
</Card>

<style>
	@keyframes fillProgress {
		0% {
			width: 0%;
			opacity: 0.8;
		}
		100% {
			width: 100%;
			opacity: 0;
		}
	}
</style>
