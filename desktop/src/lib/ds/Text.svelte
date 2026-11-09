<!-- Typografie: nadpisy, malé kapitálky, poznámka (kurzíva), čísla, zvýraznění. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	type Variant = 'h1' | 'h2' | 'h3' | 'body' | 'caps' | 'why' | 'small' | 'big' | 'strong';
	let {
		variant = 'body',
		as,
		tone,
		num = false,
		italic = false,
		id,
		title,
		children
	}: {
		variant?: Variant;
		as?: 'p' | 'span' | 'div' | 'h1' | 'h2' | 'h3' | 'b' | 'em' | 'small';
		tone?: 'ink' | 'muted' | 'red' | 'warn';
		num?: boolean;
		italic?: boolean;
		id?: string;
		title?: string;
		children: Snippet;
	} = $props();
	const tag = $derived(as ?? ({ h1: 'h1', h2: 'h2', h3: 'h3', body: 'p', why: 'p', caps: 'span', small: 'small', big: 'span', strong: 'b' } as const)[variant]);
</script>

<svelte:element this={tag} {id} {title} class="t {variant} {tone ?? ''}" class:num class:italic>{@render children()}</svelte:element>

<style>
	.t {
		margin: 0;
	}
	.h1 {
		font-size: 26px;
		font-weight: 700;
		line-height: 1.15;
	}
	.h2 {
		font-size: 17px;
		font-weight: 500;
	}
	.h3 {
		font-size: 15px;
		font-weight: 500;
	}
	.caps {
		text-transform: uppercase;
		letter-spacing: 0.14em;
		font-size: 11px;
		font-weight: 700;
		color: var(--ink-2);
	}
	.why {
		font-size: 13px;
		color: var(--ink-2);
		font-style: italic;
		line-height: 1.38;
	}
	.small {
		font-size: 12px;
		color: var(--ink-2);
	}
	.big {
		font-size: 30px;
		font-weight: 500;
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.strong {
		font-weight: 500;
	}
	.num {
		font-variant-numeric: tabular-nums;
	}
	.italic {
		font-style: italic;
	}
	.ink {
		color: var(--ink);
	}
	.muted {
		color: var(--ink-2);
	}
	.red {
		color: var(--red);
	}
	.warn {
		color: var(--warn);
	}
</style>
