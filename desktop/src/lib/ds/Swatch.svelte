<!-- Barevný čtvereček jazyka nebo rodiny. -->
<script lang="ts">
	let { color, size = 11, label }: { color: string; size?: number; label?: string } = $props();
</script>

<span class="sw" style:background={color} style:width="{size}px" style:height="{size}px" role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : 'true'}></span>

<style>
	.sw {
		display: inline-block;
		border-radius: 1px;
		margin-right: 6px;
		flex: none;
		vertical-align: baseline;
	}
</style>
