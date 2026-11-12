<!-- Paleta příkazů (⌘K): pole hledání a seznam míst, kam skočit (obrazovky, jazyky, kraje, rok).
     Hledá bez ohledu na diakritiku a velikost písmen, ↑/↓ vybírá, Enter skočí, Esc zavře.
     Obrazovka dodá položky (a případně dynamické podle dotazu) a co se stane po výběru. -->
<script lang="ts" module>
	export interface Command {
		id: string;
		label: string;
		/** skupina v seznamu (Obrazovky, Jazyky, Kraje…) */
		group: string;
		/** šedý text vpravo */
		hint?: string;
		/** další slova pro hledání (endonym, IPA, id) */
		keywords?: string;
	}
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import { narrow, rise } from './motion';

	let {
		open = $bindable(false),
		label,
		placeholder,
		empty,
		items,
		extra,
		onpick
	}: {
		open?: boolean;
		label: string;
		placeholder: string;
		/** text, když nic neodpovídá */
		empty: string;
		items: Command[];
		/** položky podle dotazu (např. „Jít na rok −300“) */
		extra?: (query: string) => Command[];
		onpick: (command: Command) => void;
	} = $props();

	let query = $state('');
	let active = $state(0);
	let input = $state<HTMLInputElement | null>(null);
	let list = $state<HTMLUListElement | null>(null);

	const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ͡]/g, '').toLowerCase();
	const shown = $derived.by(() => {
		const q = fold(query.trim());
		const top = extra?.(query.trim()) ?? [];
		if (!q) return [...top, ...items].slice(0, 60);
		const scored: [number, Command][] = [];
		for (const c of items) {
			const l = fold(c.label), k = fold(c.keywords ?? '');
			const s = l.startsWith(q) ? 0 : l.split(/[\s·–-]+/).some((w) => w.startsWith(q)) ? 1 : l.includes(q) ? 2 : k.includes(q) ? 3 : -1;
			if (s >= 0) scored.push([s, c]);
		}
		scored.sort((a, b) => a[0] - b[0]);
		return [...top, ...scored.map((s) => s[1])].slice(0, 60);
	});
	$effect(() => {
		void query;
		active = 0;
	});
	$effect(() => {
		if (open) {
			query = '';
			void tick().then(() => input?.focus());
		}
	});
	function pick(c: Command | undefined) {
		if (!c) return;
		open = false;
		onpick(c);
	}
	function key(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			const n = shown.length;
			if (!n) return;
			active = (active + (event.key === 'ArrowDown' ? 1 : n - 1)) % n;
			void tick().then(() => list?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }));
		} else if (event.key === 'Enter') {
			event.preventDefault();
			pick(shown[active]);
		} else if (event.key === 'Escape') {
			event.preventDefault();
			open = false;
		}
	}
	const uid = $props.id();
</script>

{#if open}
	<!-- Klik vedle palety ji zavře; klávesnice má Esc. -->
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div class="veil" onclick={() => (open = false)} out:narrow={{ duration: 120 }}>
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div class="box" role="dialog" aria-label={label} tabindex="-1" onclick={(e) => e.stopPropagation()} in:rise>
			<input
				bind:this={input}
				bind:value={query}
				{placeholder}
				onkeydown={key}
				role="combobox"
				aria-expanded="true"
				aria-controls="{uid}-list"
				aria-activedescendant={shown.length ? `${uid}-${active}` : undefined}
				aria-autocomplete="list"
				spellcheck="false"
				autocomplete="off"
			/>
			<ul id="{uid}-list" role="listbox" aria-label={label} bind:this={list}>
				{#each shown as c, i (c.id)}
					{#if i === 0 || shown[i - 1].group !== c.group}<li class="group" role="presentation">{c.group}</li>{/if}
					<li id="{uid}-{i}" role="option" aria-selected={i === active} onmousemove={() => (active = i)} onclick={() => pick(c)}>
						<span>{c.label}</span>{#if c.hint}<small>{c.hint}</small>{/if}
					</li>
				{:else}
					<li class="none" role="presentation">{empty}</li>
				{/each}
			</ul>
		</div>
	</div>
{/if}

<style>
	.veil {
		position: fixed;
		inset: 0;
		z-index: 60;
		background: var(--shade);
		display: grid;
		justify-items: center;
		align-items: start;
		padding-top: 14vh;
	}
	.box {
		width: min(560px, calc(100vw - 32px));
		background: var(--land);
		border: 1px solid var(--ink);
		border-radius: var(--radius);
		box-shadow: 0 16px 40px var(--shade);
		display: grid;
		grid-template-rows: auto minmax(0, 1fr);
		max-height: 60vh;
	}
	input {
		border: 0;
		border-bottom: 1px solid var(--rule);
		background: none;
		padding: 12px 14px;
		font-size: 16px;
		outline: none;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 4px 0 8px;
		overflow: auto;
	}
	li[role='option'] {
		display: flex;
		align-items: baseline;
		gap: 12px;
		padding: 6px 14px;
		cursor: pointer;
		transition: background var(--t-tick);
	}
	li[aria-selected='true'] {
		background: var(--sel);
		box-shadow: inset 2px 0 0 var(--ink);
	}
	li span {
		flex: 1;
		min-width: 0;
	}
	small {
		font-size: 12px;
		color: var(--ink-2);
		font-style: italic;
	}
	.group {
		padding: 10px 14px 2px;
		font-size: 11px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-2);
	}
	.none {
		padding: 10px 14px;
		color: var(--ink-2);
		font-style: italic;
	}
</style>
