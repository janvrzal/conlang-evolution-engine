<script lang="ts">
	import type { Snippet } from 'svelte';
	let {
		href,
		onclick,
		current = false,
		meta,
		children
	}: { href?: string; onclick?: () => void; current?: boolean; meta?: string; children: Snippet } = $props();
</script>

<li>
	{#if href}
		<a {href} aria-current={current ? 'true' : undefined}><span>{@render children()}</span>{#if meta}<small>{meta}</small>{/if}</a>
	{:else if onclick}
		<button type="button" aria-current={current ? 'true' : undefined} {onclick}><span>{@render children()}</span>{#if meta}<small>{meta}</small>{/if}</button>
	{:else}
		<div class="static"><span>{@render children()}</span>{#if meta}<small>{meta}</small>{/if}</div>
	{/if}
</li>

<style>
	li {
		border-bottom: 1px solid var(--rule);
	}
	a,
	button,
	.static {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 10px;
		width: 100%;
		min-height: 32px;
		padding: 6px;
		background: none;
		border: 0;
		text-align: left;
		text-decoration: none;
		font-size: 14px;
	}
	a,
	button {
		cursor: pointer;
	}
	a:hover,
	button:hover {
		background: var(--field);
	}
	[aria-current='true'] {
		background: var(--sel);
		box-shadow: inset 2px 0 0 var(--ink);
		font-weight: 500;
	}
	small {
		color: var(--ink-2);
		font-variant-numeric: tabular-nums;
		font-weight: 400;
		font-size: 12px;
	}
</style>
