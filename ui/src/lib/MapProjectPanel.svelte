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
		isLoading,
		errorMessage = '',
		onAddLanguage,
		onRunSimulation,
		onExport,
		onImportLegacy
	}: {
		currentYear: number;
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
