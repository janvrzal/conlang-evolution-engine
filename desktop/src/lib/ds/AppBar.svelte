<!-- Horní lišta: projekt, dvě poloviny navigace (Zadání | Výsledek), stav běhu a průběh. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	export interface NavItem {
		href: string;
		label: string;
		current?: boolean;
		/** done = vyplněno, todo = chybí, stale = změněno od běhu */
		mark?: 'done' | 'todo' | 'stale' | null;
	}
	let {
		project,
		spec,
		results,
		specLabel,
		resultsLabel,
		status,
		tools,
		progress = null
	}: {
		project: { name: string; note?: string; href?: string };
		spec: NavItem[];
		results: NavItem[];
		specLabel: string;
		resultsLabel: string;
		status?: Snippet;
		tools?: Snippet;
		/** 0–1 při běhu, jinak null */
		progress?: number | null;
	} = $props();
</script>

<header class="bar">
	<a class="project" href={project.href ?? '/'}>{project.name}{#if project.note}<small>{project.note}</small>{/if}</a>
	<nav class="half" aria-label={specLabel}>
		<span class="caps">{specLabel}</span>
		{#each spec as item (item.href)}
			<a href={item.href} aria-current={item.current ? 'page' : undefined}
				>{#if item.mark}<span class="mk {item.mark}" aria-hidden="true"></span>{/if}{item.label}</a
			>
		{/each}
	</nav>
	<span class="sep" aria-hidden="true"></span>
	<nav class="half" aria-label={resultsLabel}>
		<span class="caps">{resultsLabel}</span>
		{#each results as item (item.href)}
			<a href={item.href} aria-current={item.current ? 'page' : undefined}
				>{#if item.mark}<span class="mk {item.mark}" aria-hidden="true"></span>{/if}{item.label}</a
			>
		{/each}
	</nav>
	<div class="status" role="status">{#if status}{@render status()}{/if}</div>
	{#if tools}<div class="tools">{@render tools()}</div>{/if}
	{#if progress != null}<div class="progress" style:width="{Math.max(0, Math.min(1, progress)) * 100}%" aria-hidden="true"></div>{/if}
</header>

<style>
	.bar {
		display: flex;
		align-items: center;
		gap: 8px 14px;
		flex-wrap: wrap;
		padding: 8px 16px;
		border-bottom: 1px solid var(--ink);
		position: relative;
		min-height: 52px;
	}
	.project {
		display: flex;
		align-items: baseline;
		gap: 8px;
		font-size: 21px;
		font-style: italic;
		text-decoration: none;
		padding: 4px 6px;
		border-radius: var(--radius);
	}
	.project:hover {
		background: var(--field);
	}
	.project small {
		font-style: normal;
		font-size: 12px;
		color: var(--ink-2);
	}
	.half {
		display: flex;
		align-items: center;
		gap: 0 2px;
		flex-wrap: wrap;
	}
	.caps {
		text-transform: uppercase;
		letter-spacing: 0.14em;
		font-size: 10px;
		font-weight: 700;
		color: var(--ink-2);
		margin-right: 6px;
	}
	.half a {
		color: var(--ink-2);
		text-decoration: none;
		font-size: 15px;
		padding: 6px 7px;
		min-height: 32px;
		display: inline-flex;
		align-items: center;
		gap: 5px;
		border-radius: var(--radius);
	}
	.half a:hover {
		color: var(--ink);
		background: var(--field);
	}
	.half a[aria-current='page'] {
		color: var(--ink);
		font-weight: 500;
		box-shadow: inset 0 -2.5px 0 var(--ink);
		border-radius: 0;
	}
	.mk {
		width: 7px;
		height: 7px;
	}
	.mk.done {
		border-radius: 50%;
		background: var(--ink-2);
	}
	.mk.todo {
		border-radius: 50%;
		border: 1.5px solid var(--ink-2);
	}
	.mk.stale {
		background: var(--red);
		transform: rotate(45deg);
	}
	.sep {
		width: 1px;
		height: 26px;
		background: var(--rule);
	}
	.status {
		margin-left: auto;
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 10px;
		font-size: 13px;
		line-height: 1.25;
		color: var(--ink-2);
		flex: 0 1 230px;
		min-width: 0;
		text-align: right;
	}
	.status :global(b) {
		color: var(--ink);
		font-weight: 500;
	}
	.tools {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.progress {
		position: absolute;
		left: 0;
		bottom: -1px;
		height: 3px;
		background: var(--ink);
		transition: width var(--t-flow) linear;
	}
</style>
