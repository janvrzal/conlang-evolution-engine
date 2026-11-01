<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	// Práce začíná světem.
	onMount(() => goto('/svet', { replaceState: true }));
</script>
