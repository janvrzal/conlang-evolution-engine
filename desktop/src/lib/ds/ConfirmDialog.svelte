<!-- Potvrzovací dialog (modální). Pro akce, které něco zahodí: neuložené změny, přepsání.
     Smazání v zadání se nepotvrzuje, vrací se hláškou Vrátit. Esc = zrušit, Enter = potvrdit. -->
<script lang="ts">
	let {
		open,
		title,
		message,
		confirmLabel,
		cancelLabel,
		danger = false,
		onconfirm,
		oncancel
	}: {
		open: boolean;
		title: string;
		message: string;
		confirmLabel: string;
		cancelLabel: string;
		danger?: boolean;
		onconfirm: () => void;
		oncancel: () => void;
	} = $props();

	let dialog: HTMLDialogElement;
	let confirmButton: HTMLButtonElement;
	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) {
			dialog.showModal();
			// bezpečná volba (Zrušit) má výchozí fokus, když potvrzení něco zahodí
			if (!danger) confirmButton?.focus();
		} else if (!open && dialog.open) dialog.close();
	});
</script>

<dialog bind:this={dialog} aria-labelledby="confirm-title" aria-describedby="confirm-message" oncancel={(e) => { e.preventDefault(); oncancel(); }}>
	<h2 id="confirm-title">{title}</h2>
	<p id="confirm-message">{message}</p>
	<div class="actions">
		<button type="button" class="btn quiet" onclick={oncancel}>{cancelLabel}</button>
		<button type="button" class="btn primary" class:danger bind:this={confirmButton} onclick={onconfirm}>{confirmLabel}</button>
	</div>
</dialog>

<style>
	dialog {
		border: 1px solid var(--ink);
		border-radius: var(--radius);
		background: var(--land);
		color: var(--ink);
		box-shadow: 0 10px 30px var(--shade);
		padding: 18px 20px 14px;
		max-width: min(460px, calc(100vw - 32px));
		display: grid;
		gap: 10px;
	}
	dialog:not([open]) {
		display: none;
	}
	dialog::backdrop {
		background: var(--shade);
	}
	h2 {
		margin: 0;
		font-size: 19px;
		font-weight: 500;
	}
	p {
		font-size: 14px;
		line-height: 1.45;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 6px;
	}
	.btn {
		display: inline-flex;
		align-items: center;
		min-height: 32px;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 4px 14px;
		cursor: pointer;
		font-size: 14px;
		background: var(--field);
		color: var(--ink);
	}
	.quiet {
		background: none;
		border-color: transparent;
		color: var(--ink-2);
	}
	.quiet:hover {
		color: var(--ink);
		border-color: var(--rule);
	}
	.primary {
		background: var(--ink);
		color: var(--panel);
		border-color: var(--ink);
	}
	.primary.danger {
		background: var(--red);
		border-color: var(--red);
	}
</style>
