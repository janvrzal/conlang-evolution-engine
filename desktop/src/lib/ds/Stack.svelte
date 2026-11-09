<!-- Svislé skládání s mezerou podle stupnice (1 = 4 px … 5 = 24 px). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		gap = 2,
		align = 'stretch',
		label,
		role,
		children
	}: { gap?: 0 | 1 | 2 | 3 | 4 | 5; align?: 'stretch' | 'start' | 'center' | 'end'; label?: string; role?: string; children: Snippet } = $props();
</script>

<div class="stack" {role} aria-label={label} style:gap={gap ? `var(--gap-${gap})` : '0'} style:justify-items={align}>
	{@render children()}
</div>

<style>
	.stack {
		display: grid;
		min-width: 0;
		align-content: start;
	}
</style>
