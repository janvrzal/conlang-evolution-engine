<!-- Krátká hláška vpravo dole s volitelnou akcí Vrátit (smazání se nepotvrzuje dialogem). -->
<script lang="ts">
	import { narrow, sprout } from './motion';
	let {
		message,
		actionLabel,
		onaction,
		shortcut
	}: { message: string; actionLabel?: string; onaction?: () => void; shortcut?: string } = $props();
</script>

<div class="toast" role="status" in:sprout out:narrow>
	<span>{message}</span>
	{#if actionLabel && onaction}<button type="button" onclick={onaction}>{actionLabel}</button>{/if}
	{#if shortcut}<kbd>{shortcut}</kbd>{/if}
</div>

<style>
	.toast {
		position: fixed;
		right: 16px;
		bottom: 84px;
		z-index: 20;
		display: inline-flex;
		align-items: center;
		gap: 14px;
		background: var(--ink);
		color: var(--panel);
		padding: 8px 10px 8px 16px;
		border-radius: var(--radius);
		font-size: 14px;
		box-shadow: 0 8px 24px var(--shade);
	}
	button {
		background: none;
		border: 0;
		color: var(--panel);
		font-weight: 500;
		text-decoration: underline;
		cursor: pointer;
		min-height: 24px;
	}
	kbd {
		border: 1px solid var(--panel);
		border-radius: var(--radius);
		font-size: 11px;
		font-weight: 700;
		padding: 0 5px;
		line-height: 18px;
		font-family: var(--f-ui);
	}
</style>
