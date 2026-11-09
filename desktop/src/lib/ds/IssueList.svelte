<!-- Hlášení ověření zadání: chyby (červený kosočtverec) a upozornění (kroužek). -->
<script lang="ts">
	export interface IssueItem {
		severity: 'error' | 'warning';
		/** kde: „Dějiny · Školy 1150“ */
		place?: string;
		href?: string;
		message: string;
		/** cesta ve specifikaci, např. events.28 */
		code?: string;
		/** odkud hlášení je (engine, kalibrace) */
		source?: string;
	}
	let { items }: { items: IssueItem[] } = $props();
</script>

<ul class="issues">
	{#each items as item, i (i)}
		<li class={item.severity === 'error' ? 'e' : 'w'}>
			<span
				>{#if item.place}{#if item.href}<a href={item.href}><b>{item.place}:</b></a>{:else}<b>{item.place}:</b>{/if}{' '}{/if}{item.message}{#if item.code}{' '}<code
						>{item.code}</code
					>{/if}{#if item.source}{' '}<em>{item.source}</em>{/if}</span
			>
		</li>
	{/each}
</ul>

<style>
	.issues {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
	}
	li {
		display: grid;
		grid-template-columns: 14px minmax(0, 1fr);
		gap: 8px;
		padding: 8px 0;
		border-bottom: 1px solid var(--rule);
		font-size: 14px;
	}
	li::before {
		content: '';
		width: 8px;
		height: 8px;
		margin-top: 6px;
	}
	.e::before {
		background: var(--red);
		transform: rotate(45deg);
	}
	.w::before {
		border: 1.5px solid var(--warn);
		border-radius: 50%;
	}
	b {
		font-weight: 500;
	}
	code {
		font-size: 12px;
		color: var(--ink-2);
	}
	em {
		font-size: 12px;
		color: var(--ink-2);
	}
</style>
