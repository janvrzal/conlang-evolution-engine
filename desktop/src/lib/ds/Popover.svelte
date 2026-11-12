<!-- Vyskakovací panel nad prvkem (seznam hlášení nad patou). Rodič musí být <Footer> nebo jiný relativní kontejner z ds. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { narrow, rise } from './motion';
	let { label, open = true, width = 560, children }: { label: string; open?: boolean; width?: number; children: Snippet } = $props();
</script>

{#if open}
	<div class="pop" role="dialog" in:rise out:narrow aria-label={label} style:width="{width}px">{@render children()}</div>
{/if}

<style>
	.pop {
		position: absolute;
		left: 16px;
		bottom: calc(100% + 6px);
		z-index: 5;
		max-width: calc(100vw - 32px);
		background: var(--land);
		border: 1px solid var(--ink);
		border-radius: var(--radius);
		box-shadow: 0 10px 30px var(--shade);
		padding: 12px 14px;
		display: grid;
		gap: 6px;
	}
</style>
