<script lang="ts">
	import { Upload } from 'lucide-svelte';
	import type { WorldMapDocument } from './types';
	let { onImport }: { onImport?: (document: WorldMapDocument) => void } = $props();
	let error = $state('');
	function read(event: Event) {
		const input = event.currentTarget as HTMLInputElement; const file = input.files?.[0]; input.value = '';
		if (!file) return; if (!['image/png','image/jpeg','image/webp','image/svg+xml'].includes(file.type)) { error = 'Podporován je PNG, JPEG, WebP nebo SVG.'; return; }
		const url = URL.createObjectURL(file); error = ''; onImport?.({ name: file.name, width: 2400, height: 1400, backgroundUrl: url });
	}
</script>
<div class="space-y-2"><label class="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed px-3 py-4 text-sm hover:bg-muted"><Upload class="h-4 w-4" />Importovat podklad<input class="sr-only" type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onchange={read} /></label>{#if error}<p class="text-xs text-destructive">{error}</p>{/if}<p class="text-xs text-muted-foreground">Pouze vizuální podklad; import nemění jazyky ani genealogii.</p></div>
