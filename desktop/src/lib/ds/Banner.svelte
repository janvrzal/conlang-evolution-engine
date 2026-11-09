<!-- Pruh pod lištou: zastaralé výsledky, engine offline. Akce vpravo. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	let { tone = 'stale', actions, children }: { tone?: 'stale' | 'error' | 'info'; actions?: Snippet; children: Snippet } = $props();
</script>

<div class="banner {tone}" role={tone === 'error' ? 'alert' : 'status'}>
	<span class="mark" aria-hidden="true"></span>
	<span class="text">{@render children()}</span>
	{#if actions}<span class="actions">{@render actions()}</span>{/if}
</div>

<style>
	.banner {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 14px;
		border-bottom: 1px solid var(--rule);
		font-size: 14px;
	}
	.stale,
	.error {
		background: var(--tint);
	}
	.info {
		background: var(--field);
	}
	.mark {
		width: 8px;
		height: 8px;
		background: var(--red);
		transform: rotate(45deg);
		flex: none;
	}
	.info .mark {
		background: var(--ink-2);
		border-radius: 50%;
		transform: none;
	}
	.text {
		flex: 1;
	}
	.text :global(b) {
		font-weight: 500;
	}
	.actions {
		display: flex;
		gap: 8px;
	}
</style>
