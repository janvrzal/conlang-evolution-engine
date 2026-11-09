<!-- Vodorovná řada, která se zalamuje. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		gap = 2,
		align = 'center',
		justify = 'start',
		wrap = true,
		label,
		role,
		children
	}: {
		gap?: 0 | 1 | 2 | 3 | 4 | 5;
		align?: 'center' | 'baseline' | 'start' | 'end' | 'stretch';
		justify?: 'start' | 'between' | 'end' | 'center';
		wrap?: boolean;
		label?: string;
		role?: string;
		children: Snippet;
	} = $props();
	const just = $derived(justify === 'between' ? 'space-between' : justify === 'start' ? 'flex-start' : justify === 'end' ? 'flex-end' : 'center');
</script>

<div
	class="cluster"
	{role}
	aria-label={label}
	style:gap={gap ? `var(--gap-${gap})` : '0'}
	style:align-items={align === 'start' ? 'flex-start' : align === 'end' ? 'flex-end' : align}
	style:justify-content={just}
	style:flex-wrap={wrap ? 'wrap' : 'nowrap'}
>
	{@render children()}
</div>

<style>
	.cluster {
		display: flex;
		min-width: 0;
	}
</style>
