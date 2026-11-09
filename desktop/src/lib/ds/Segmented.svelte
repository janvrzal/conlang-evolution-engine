<!-- Přepínač jedné z možností (vrstva mapy, rodina, pozadí dějin). -->
<script lang="ts" generics="V extends string | number">
	let {
		options,
		value = $bindable(),
		label,
		vertical = false,
		onchange
	}: {
		options: { value: V; label: string; title?: string; disabled?: boolean }[];
		value: V;
		label: string;
		vertical?: boolean;
		onchange?: (value: V) => void;
	} = $props();

	function pick(next: V, disabled?: boolean) {
		if (disabled) return;
		value = next;
		onchange?.(next);
	}
</script>

<div class="seg" class:vertical role="group" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			aria-pressed={option.value === value}
			aria-disabled={option.disabled ? 'true' : undefined}
			title={option.title}
			onclick={() => pick(option.value, option.disabled)}>{option.label}</button
		>
	{/each}
</div>

<style>
	.seg {
		display: flex;
		flex-wrap: wrap;
	}
	.vertical {
		flex-direction: column;
		align-items: flex-start;
	}
	button {
		background: none;
		border: 0;
		min-height: 30px;
		padding: 4px 10px;
		cursor: pointer;
		font-size: 14px;
		color: var(--ink-2);
		border-bottom: 2px solid transparent;
	}
	button[aria-pressed='true'] {
		color: var(--ink);
		font-weight: 500;
		border-bottom-color: var(--ink);
	}
	button:hover {
		color: var(--ink);
	}
	button[aria-disabled='true'] {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
