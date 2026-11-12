<!-- Čekání na dosimulování: mřížka 3×3 vsí, kterou se šíří vlna změny z rohu (zdrojová ves červeně).
     Jen CSS; při omezeném pohybu stojí. Text vedle dodá obrazovka. -->
<script lang="ts">
	let { label }: { label?: string } = $props();
</script>

<span class="work" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : 'true'}>
	{#each [0, 1, 2, 3, 4, 5, 6, 7, 8] as i (i)}<i style:animation-delay="{((i % 3) + Math.floor(i / 3)) * 0.13}s"></i>{/each}
</span>

<style>
	.work {
		display: inline-grid;
		grid-template-columns: repeat(3, 5px);
		gap: 3px;
		flex: none;
		vertical-align: middle;
	}
	i {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		background: var(--ink);
		transform: scale(0.45);
		animation: wave 1.6s var(--e-change) infinite;
	}
	i:first-child {
		background: var(--red);
	}
	@keyframes wave {
		30% {
			transform: scale(1);
		}
		60% {
			transform: scale(0.45);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		i {
			animation: none;
			transform: scale(0.75);
		}
	}
</style>
