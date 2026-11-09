<!-- Posuvník hodnoty. -->
<script lang="ts">
	let {
		value = $bindable(),
		min,
		max,
		step = 1,
		label,
		id,
		oninput
	}: { value: number; min: number; max: number; step?: number; label?: string; id?: string; oninput?: (value: number) => void } = $props();
</script>

<input type="range" {id} {min} {max} {step} aria-label={label} bind:value oninput={() => oninput?.(value)} />

<style>
	input {
		width: 100%;
		accent-color: var(--ink);
	}
</style>
