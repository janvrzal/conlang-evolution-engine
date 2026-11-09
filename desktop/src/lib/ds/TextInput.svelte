<!-- Textové, hledací nebo číselné pole. -->
<script lang="ts">
	let {
		value = $bindable(),
		type = 'text',
		id,
		label,
		placeholder,
		invalid = false,
		describedby,
		width = 'full',
		min,
		max,
		step,
		onchange,
		oninput,
		ipa = false
	}: {
		/** zápis výslovnosti písmem Charis */
		ipa?: boolean;
		value: string | number;
		type?: 'text' | 'search' | 'number';
		id?: string;
		/** aria-label, když pole nemá <Field label> */
		label?: string;
		placeholder?: string;
		invalid?: boolean;
		describedby?: string;
		width?: 's' | 'm' | 'l' | 'full';
		min?: number;
		max?: number;
		step?: number;
		onchange?: (value: string | number) => void;
		oninput?: (value: string | number) => void;
	} = $props();
</script>

<input
	class="input {width}"
	class:num={type === 'number'}
	class:err={invalid}
	class:ipa
	{type}
	{id}
	{placeholder}
	{min}
	{max}
	{step}
	aria-label={label}
	aria-invalid={invalid ? 'true' : undefined}
	aria-describedby={describedby}
	bind:value
	onchange={() => onchange?.(value)}
	oninput={() => oninput?.(value)}
/>

<style>
	.input {
		background: var(--field);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 5px 8px;
		min-height: 32px;
	}
	.s {
		width: 96px;
	}
	.m {
		width: 160px;
	}
	.l {
		width: 240px;
	}
	.full {
		width: 100%;
	}
	.num {
		font-variant-numeric: tabular-nums;
	}
	.ipa {
		font-family: var(--f-ipa);
		font-size: 16px;
	}
	.err {
		border-color: var(--red);
	}
</style>
