<!-- Plocha pro mapu či graf s plovoucími panely v rozích (tl, tr, bl, br). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		tone = 'sea',
		minHeight = 400,
		tl,
		tr,
		bl,
		br,
		children
	}: { label: string; tone?: 'sea' | 'land'; minHeight?: number; tl?: Snippet; tr?: Snippet; bl?: Snippet; br?: Snippet; children: Snippet } = $props();
</script>

<section class="stage {tone}" aria-label={label} style:min-height="{minHeight}px">
	{@render children()}
	{#if tl}<div class="corner tl">{@render tl()}</div>{/if}
	{#if tr}<div class="corner tr">{@render tr()}</div>{/if}
	{#if bl}<div class="corner bl">{@render bl()}</div>{/if}
	{#if br}<div class="corner br">{@render br()}</div>{/if}
</section>

<style>
	.stage {
		position: relative;
		border-radius: var(--radius);
		overflow: hidden;
		flex: 1 1 auto;
		min-width: 0;
	}
	.sea {
		background: var(--sea);
	}
	.land {
		background: var(--land);
	}
	.corner {
		position: absolute;
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		max-width: calc(100% - 24px);
		pointer-events: none;
	}
	.corner > :global(*) {
		pointer-events: auto;
	}
	.tl {
		left: 14px;
		top: 12px;
	}
	.tr {
		right: 10px;
		top: 10px;
		justify-content: flex-end;
	}
	.bl {
		left: 12px;
		bottom: 12px;
	}
	.br {
		right: 12px;
		bottom: 12px;
		justify-content: flex-end;
	}
</style>
