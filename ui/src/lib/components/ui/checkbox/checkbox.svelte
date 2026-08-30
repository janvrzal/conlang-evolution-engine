<script lang="ts">
	import type { HTMLInputAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils';
	let {
		class: className,
		checked = $bindable(false),
		...rest
	}: HTMLInputAttributes & { checked?: boolean; class?: string } = $props();
</script>

<input
	type="checkbox"
	bind:checked
	class={cn(
		'h-4 w-4 rounded border-input accent-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
		className
	)}
	{...rest}
/>
