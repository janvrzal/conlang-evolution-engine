<!-- Souhrn ověření v patě: „Bez chyb · 2 upozornění“ nebo „1 chyba“. Otevírá seznam hlášení. -->
<script lang="ts">
	let {
		ok,
		text,
		href,
		expanded,
		onclick
	}: { ok: boolean; text: string; href?: string; expanded?: boolean; onclick?: () => void } = $props();
</script>

{#if href}
	<a class="check" class:bad={!ok} {href}>{text}</a>
{:else}
	<button type="button" class="check" class:bad={!ok} aria-expanded={expanded} {onclick}>{text}</button>
{/if}

<style>
	.check {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 32px;
		padding: 4px 10px;
		border-radius: var(--radius);
		text-decoration: none;
		background: none;
		border: 0;
		cursor: pointer;
		font-size: 13px;
		color: var(--ink-2);
	}
	.check::before {
		content: '';
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--ink-2);
	}
	.bad {
		color: var(--red);
		background: var(--tint);
	}
	.bad::before {
		border-radius: 0;
		background: var(--red);
		transform: rotate(45deg);
	}
</style>
