<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import { onMount } from 'svelte';
	import { i18n, restoreLocale, setLocale } from '$lib/i18n.svelte';
	import { Button } from '$lib/components/ui/button';
	import '../app.css';

	let { children } = $props();
	onMount(restoreLocale);
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="flex flex-col min-h-screen">
	<div class="fixed right-4 top-4 z-50 rounded-md border bg-card p-1 shadow-sm">
		<Button
			variant={i18n.locale === 'cs' ? 'secondary' : 'ghost'}
			size="sm"
			class="h-7 px-2 text-xs"
			onclick={() => setLocale('cs')}>Česky</Button
		>
		<Button
			variant={i18n.locale === 'en' ? 'secondary' : 'ghost'}
			size="sm"
			class="h-7 px-2 text-xs"
			onclick={() => setLocale('en')}>EN</Button
		>
	</div>
	{@render children()}
</div>
