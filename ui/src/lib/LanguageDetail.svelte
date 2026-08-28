<script lang="ts">
	import { evolveLanguage, resetApiBase } from '$lib/api';
	import { X, Loader2, ArrowRight, Import } from 'lucide-svelte';

	type TraceStep = { year: number; form: string; rule_name: string | null; note: string | null };
	type Epoch = { year: number; label: string | null; words: Record<string, string>; inventory: string[] };
	type SoundChange = {
		kind: 'sound_change';
		year: number;
		rule_name: string;
		hit_count: number;
		changes: { concept_id: string; before: string; after: string }[];
	};
	type Borrowing = { kind: 'borrowing'; year: number; source_id: string; concepts: string[] };
	type Event = SoundChange | Borrowing | { kind: string; year: number };

	let {
		nodeId,
		label,
		biome = null,
		years = 1000,
		lexicon = [],
		onclose
	} = $props<{
		nodeId: string;
		label: string;
		biome?: string | null;
		years?: number;
		lexicon?: { id: string; ipa: string }[];
		onclose: () => void;
	}>();

	let loading = $state(false);
	let error = $state<string | null>(null);
	let epochs = $state<Epoch[]>([]);
	let events = $state<Event[]>([]);
	let traces = $state<Record<string, TraceStep[]>>({});
	let openConcept = $state<string | null>(null);

	let soundChanges = $derived(events.filter((e): e is SoundChange => e.kind === 'sound_change'));
	let borrowings = $derived(events.filter((e): e is Borrowing => e.kind === 'borrowing'));
	let concepts = $derived(Object.keys(traces).sort());
	let firstEpoch = $derived(epochs[0]);
	let lastEpoch = $derived(epochs[epochs.length - 1]);

	// Znovu načteme pokaždé, když se změní uzel nebo parametry vývoje.
	$effect(() => {
		const payload = {
			proto_lexicon: lexicon,
			years,
			biome,
			node_id: nodeId
		};
		void load(payload);
	});

	async function load(payload: Record<string, unknown>) {
		if (!lexicon.length) {
			error = 'Nejprve vygeneruj proto-slovník v sekci Metaeditace.';
			epochs = [];
			events = [];
			traces = {};
			return;
		}

		loading = true;
		error = null;
		try {
			const data = await evolveLanguage(payload);
			epochs = data.epochs ?? [];
			events = data.events ?? [];
			traces = data.traces ?? {};
		} catch (e) {
			resetApiBase();
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	}

	function toggle(concept: string) {
		openConcept = openConcept === concept ? null : concept;
	}

	/** Podíl slovníku, který dané pravidlo zasáhlo — pro sílu proužku. */
	function share(change: SoundChange): number {
		const total = Object.keys(firstEpoch?.words ?? {}).length || 1;
		return Math.min(1, change.hit_count / total);
	}
</script>

<aside class="detail">
	<header>
		<div>
			<h2>{label}</h2>
			<p class="sub">
				{#if biome}<span class="tag">{biome}</span>{/if}
				<span>{years} let vývoje</span>
			</p>
		</div>
		<button class="icon" onclick={onclose} aria-label="Zavřít panel"><X size={16} /></button>
	</header>

	{#if loading}
		<div class="state"><Loader2 size={18} class="spin" /> Počítám vývoj…</div>
	{:else if error}
		<div class="state error">{error}</div>
	{:else if !epochs.length}
		<div class="state">Zatím není co ukázat.</div>
	{:else}
		<section>
			<h3>Epochy</h3>
			<div class="epochs">
				{#each epochs as epoch (epoch.year)}
					<div class="epoch">
						<span class="year">{epoch.year}</span>
						<span class="name">{epoch.label ?? ''}</span>
						<span class="inv">{epoch.inventory.length} fonémů</span>
					</div>
				{/each}
			</div>
		</section>

		<section>
			<h3>Zvukové změny <span class="count">{soundChanges.length}</span></h3>
			{#if !soundChanges.length}
				<p class="empty">Jazyk zůstal beze změny.</p>
			{:else}
				<ol class="changes">
					{#each soundChanges as change (change.year + change.rule_name)}
						<li>
							<div class="change-head">
								<span class="year">{change.year}</span>
								<span class="rule">{change.rule_name.replace(/\s*\(gen\. v \d+\)/, '')}</span>
								<span class="hits">{change.hit_count}×</span>
							</div>
							<div class="bar"><i style="width: {share(change) * 100}%"></i></div>
							<div class="examples">
								{#each change.changes.slice(0, 3) as ex (ex.concept_id)}
									<span class="ex">
										<b>{ex.before}</b><ArrowRight size={11} /><b>{ex.after || '∅'}</b>
									</span>
								{/each}
								{#if change.changes.length > 3}
									<span class="more">+{change.changes.length - 3} dalších</span>
								{/if}
							</div>
						</li>
					{/each}
				</ol>
			{/if}
		</section>

		{#if borrowings.length}
			<section>
				<h3>Výpůjčky <span class="count">{borrowings.length}</span></h3>
				<ul class="loans">
					{#each borrowings as loan (loan.year + loan.source_id)}
						<li>
							<span class="year">{loan.year}</span>
							<Import size={12} />
							<span class="from">z <b>{loan.source_id}</b></span>
							<span class="what">{loan.concepts.join(', ')}</span>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		<section>
			<h3>Slovník <span class="count">{concepts.length}</span></h3>
			<p class="hint">Klikni na slovo a uvidíš, čím prošlo.</p>
			<ul class="words">
				{#each concepts as concept (concept)}
					{@const from = firstEpoch?.words?.[concept] ?? '—'}
					{@const to = lastEpoch?.words?.[concept] ?? '—'}
					<li class:changed={from !== to}>
						<button class="word" onclick={() => toggle(concept)}>
							<span class="concept">{concept}</span>
							<span class="forms">
								<b>{from}</b>
								{#if from !== to}<ArrowRight size={11} /><b class="now">{to}</b>{/if}
							</span>
						</button>
						{#if openConcept === concept}
							<ol class="trace">
								{#each traces[concept] as step, i (i)}
									<li>
										<span class="year">{step.year}</span>
										<span class="form">{step.form || '—'}</span>
										<span class="why">
											{step.rule_name?.replace(/\s*\(gen\. v \d+\)/, '') ?? step.note ?? ''}
										</span>
									</li>
								{:else}
									<li class="empty-step">Tvar se nikdy nezměnil.</li>
								{/each}
							</ol>
						{/if}
					</li>
				{/each}
			</ul>
		</section>
	{/if}
</aside>

<style>
	.detail {
		width: 380px;
		height: 100%;
		display: flex;
		flex-direction: column;
		gap: 4px;
		overflow-y: auto;
		background: hsl(var(--card, 0 0% 100%));
		border-left: 1px solid hsl(var(--border, 0 0% 90%));
		font-size: 13px;
	}

	header {
		position: sticky;
		top: 0;
		z-index: 1;
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
		padding: 16px;
		background: inherit;
		border-bottom: 1px solid hsl(var(--border, 0 0% 90%));
	}

	h2 {
		margin: 0;
		font-size: 15px;
		font-weight: 600;
	}

	.sub {
		margin: 4px 0 0;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 11px;
		opacity: 0.65;
	}

	.tag {
		padding: 1px 6px;
		border-radius: 999px;
		border: 1px solid hsl(var(--border, 0 0% 90%));
	}

	.icon {
		display: grid;
		place-items: center;
		width: 26px;
		height: 26px;
		border-radius: 6px;
		border: none;
		background: transparent;
		cursor: pointer;
		opacity: 0.6;
	}

	.icon:hover {
		opacity: 1;
		background: hsl(var(--muted, 0 0% 96%));
	}

	section {
		padding: 14px 16px;
		border-bottom: 1px solid hsl(var(--border, 0 0% 90%) / 0.6);
	}

	h3 {
		margin: 0 0 10px;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		opacity: 0.55;
	}

	.count {
		margin-left: 4px;
		opacity: 0.7;
		font-weight: 400;
	}

	.state {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 24px 16px;
		opacity: 0.7;
	}

	.state.error {
		color: #dc2626;
		opacity: 1;
	}

	:global(.spin) {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.year {
		font-variant-numeric: tabular-nums;
		opacity: 0.5;
		font-size: 11px;
		min-width: 34px;
	}

	/* Epochy */
	.epochs {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.epoch {
		display: grid;
		grid-template-columns: 40px 1fr auto;
		align-items: center;
		gap: 8px;
		padding: 4px 6px;
		border-radius: 5px;
	}

	.epoch:nth-child(odd) {
		background: hsl(var(--muted, 0 0% 96%) / 0.5);
	}

	.epoch .name {
		font-weight: 500;
	}

	.epoch .inv {
		font-size: 11px;
		opacity: 0.55;
	}

	/* Zvukové změny */
	.changes {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.change-head {
		display: flex;
		align-items: baseline;
		gap: 8px;
	}

	.rule {
		flex: 1;
		font-weight: 500;
	}

	.hits {
		font-size: 11px;
		opacity: 0.55;
		font-variant-numeric: tabular-nums;
	}

	.bar {
		height: 3px;
		margin: 5px 0;
		border-radius: 999px;
		background: hsl(var(--muted, 0 0% 96%));
		overflow: hidden;
	}

	.bar i {
		display: block;
		height: 100%;
		background: #6b7cff;
	}

	.examples {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		font-size: 11px;
	}

	.ex {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		opacity: 0.75;
	}

	.ex b {
		font-weight: 500;
	}

	.more {
		opacity: 0.45;
	}

	/* Výpůjčky */
	.loans {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.loans li {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 5px 7px;
		border-radius: 5px;
		background: #6b7cff14;
		border-left: 2px solid #6b7cff;
	}

	.loans .what {
		font-size: 11px;
		opacity: 0.7;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Slovník */
	.hint {
		margin: -4px 0 8px;
		font-size: 11px;
		opacity: 0.5;
	}

	.words {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.word {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		width: 100%;
		padding: 5px 6px;
		border: none;
		border-radius: 5px;
		background: transparent;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}

	.word:hover {
		background: hsl(var(--muted, 0 0% 96%));
	}

	.concept {
		opacity: 0.7;
	}

	.forms {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-variant-numeric: tabular-nums;
	}

	.forms b {
		font-weight: 500;
		opacity: 0.55;
	}

	.forms b.now {
		opacity: 1;
	}

	.words li:not(.changed) .forms b {
		opacity: 0.75;
	}

	.trace {
		list-style: none;
		margin: 2px 0 10px;
		padding: 8px 10px;
		border-left: 2px solid #6b7cff;
		background: hsl(var(--muted, 0 0% 96%) / 0.6);
		border-radius: 0 5px 5px 0;
		display: flex;
		flex-direction: column;
		gap: 5px;
		font-size: 11px;
	}

	.trace li {
		display: grid;
		grid-template-columns: 38px 70px 1fr;
		gap: 8px;
		align-items: baseline;
	}

	.trace .form {
		font-weight: 600;
	}

	.trace .why {
		opacity: 0.6;
	}

	.empty,
	.empty-step {
		margin: 0;
		opacity: 0.5;
		font-size: 11px;
	}
</style>
