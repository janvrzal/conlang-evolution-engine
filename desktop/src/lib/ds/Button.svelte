<!-- Tlačítko nebo odkaz vzhledu tlačítka. Zakázané je aria-disabled (zůstane vidět a čitelné). -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import Icon, { type IconName } from './Icon.svelte';

	let {
		variant = 'default',
		href,
		disabled = false,
		pressed,
		icon,
		label,
		title,
		type = 'button',
		round = false,
		onclick,
		children
	}: {
		variant?: 'default' | 'primary' | 'quiet';
		href?: string;
		disabled?: boolean;
		pressed?: boolean;
		icon?: IconName;
		/** aria-label pro tlačítko jen s ikonou */
		label?: string;
		title?: string;
		type?: 'button' | 'submit';
		round?: boolean;
		onclick?: (event: MouseEvent) => void;
		children?: Snippet;
	} = $props();

	function click(event: MouseEvent) {
		if (disabled) {
			event.preventDefault();
			return;
		}
		onclick?.(event);
	}
</script>

{#if href && !disabled}
	<a class="btn {variant}" class:round class:icon-only={!children && !!icon} {href} {title} aria-label={label} onclick={click}
		>{#if icon}<Icon name={icon} />{/if}{#if children}{@render children()}{/if}</a
	>
{:else}
	<button
		class="btn {variant}"
		class:round
		class:icon-only={!children && !!icon}
		{type}
		{title}
		aria-label={label}
		aria-disabled={disabled ? 'true' : undefined}
		aria-pressed={pressed}
		onclick={click}>{#if icon}<Icon name={icon} />{/if}{#if children}{@render children()}{/if}</button
	>
{/if}

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		min-height: 32px;
		background: var(--field);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 4px 12px;
		cursor: pointer;
		font-size: 14px;
		text-decoration: none;
		white-space: nowrap;
		color: var(--ink);
	}
	.btn:hover {
		border-color: var(--ink-2);
	}
	.primary {
		background: var(--ink);
		color: var(--panel);
		border-color: var(--ink);
	}
	.quiet {
		background: none;
		border-color: transparent;
		color: var(--ink-2);
	}
	.quiet:hover {
		color: var(--ink);
		border-color: var(--rule);
	}
	.btn[aria-disabled='true'] {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn[aria-pressed='true'] {
		border-color: var(--ink);
		box-shadow: inset 0 -2px 0 var(--ink);
	}
	.icon-only {
		padding: 4px 8px;
	}
	.round {
		width: 40px;
		height: 40px;
		padding: 0;
		border-radius: 50%;
		background: none;
		border-color: var(--ink-2);
	}
</style>
