<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';

	let { data, selected = false } = $props<{
		data: { label: string; isProto?: boolean; year?: number; biome?: string };
		selected?: boolean;
	}>();

	// Obsidian škáluje uzel podle důležitosti — protojazyk je kořen, tak je větší.
	const size = $derived(data.isProto ? 30 : 20);
</script>

<div class="node" class:proto={data.isProto} class:selected style="--size: {size}px">
	<!--
		Oba úchyty sedí ve STŘEDU kuličky, ne na jejím okraji.
		xyflow kreslí hranu mezi úchyty — s výchozími pozicemi (Top/Bottom)
		proto čára začínala nad uzlem a končila pod druhým, což u uzlů nad sebou
		vypadalo jako zakulacená smyčka. Ze středu do středu vede rovná čára
		a kulička sama překryje její začátek i konec, přesně jako v Obsidianu.
	-->
	<div class="dot">
		<Handle type="target" position={Position.Top} class="centered" />
		<Handle type="source" position={Position.Bottom} class="centered" />
	</div>
	<div class="label">
		{data.label}
		{#if data.year !== undefined}<span class="year">{data.year}</span>{/if}
	</div>
</div>

<style>
	.node {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		pointer-events: all;
		cursor: pointer;
	}

	.dot {
		position: relative;
		width: var(--size);
		height: var(--size);
		border-radius: 50%;
		background: var(--node-fill, #8a8f98);
		transition:
			transform 0.15s ease,
			background 0.15s ease,
			box-shadow 0.15s ease;
	}

	.node.proto .dot {
		background: var(--node-fill-proto, #6b7cff);
	}

	.node:hover .dot {
		transform: scale(1.18);
		box-shadow: 0 0 0 6px color-mix(in srgb, var(--node-fill, #8a8f98) 22%, transparent);
	}

	.node.selected .dot {
		background: var(--node-fill-active, #6b7cff);
		box-shadow: 0 0 0 5px color-mix(in srgb, var(--node-fill-active, #6b7cff) 30%, transparent);
	}

	.label {
		display: flex;
		align-items: baseline;
		gap: 6px;
		font-size: 12px;
		font-weight: 500;
		letter-spacing: 0.01em;
		color: var(--node-label, #b9bec7);
		white-space: nowrap;
		/* Obsidian nechává popisky čitelné nad hranami i nad plátnem. */
		text-shadow: 0 1px 3px var(--node-label-shadow, rgba(0, 0, 0, 0.55));
	}

	.node:hover .label,
	.node.selected .label {
		color: var(--node-label-active, #f2f4f8);
	}

	.year {
		font-size: 10px;
		font-variant-numeric: tabular-nums;
		opacity: 0.6;
	}

	/*
		Úchyty mají NULOVOU velikost a leží přesně ve středu kuličky.

		Proč nula: xyflow nebere střed úchytu, ale jeho okraj podle `position`
		(viz getHandlePosition v @xyflow/system) —
		    Top    -> { x: x + width/2, y }
		    Bottom -> { x: x + width/2, y + height }
		Úchyt o velikosti kuličky by tedy pořád vycházel z jejího vrcholu, resp.
		spodku. Při width = height = 0 obě větve vrátí { x, y }, tedy přesně
		bod, kam úchyt umístíme — střed kuličky. Hrana pak vede od středu ke
		středu a kulička překryje její konce, jako v Obsidianu.

		Chytací plocha se dělá přes ::after, protože pseudoelement nezvětšuje
		getBoundingClientRect() vlastního prvku, ale pointer events zachytí.
		visibility: hidden by úchyt z pointer events vyřadilo úplně.
	*/
	.node :global(.svelte-flow__handle.centered) {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 0;
		height: 0;
		min-width: 0;
		min-height: 0;
		padding: 0;
		border: none;
		background: transparent;
		transform: none;
	}

	.node :global(.svelte-flow__handle.centered)::after {
		content: '';
		position: absolute;
		/* Terč o velikosti kuličky, vycentrovaný na její střed. */
		left: calc(var(--size) / -2);
		top: calc(var(--size) / -2);
		width: var(--size);
		height: var(--size);
		border-radius: 50%;
	}

	/* Zdrojový úchyt leží navrchu, aby tažení z kuličky začalo nové spojení. */
	.node :global(.svelte-flow__handle-bottom.centered) {
		z-index: 1;
	}
</style>
