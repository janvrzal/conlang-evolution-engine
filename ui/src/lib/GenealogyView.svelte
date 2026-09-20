<script lang="ts">
	import { GitBranch, Search, ZoomIn, ZoomOut } from 'lucide-svelte';
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';

	type RawNode = { id: string; data?: Record<string, any> };
	type RawEdge = { id?: string; source: string; target: string; type?: string; data?: Record<string, any> };
	type Snapshot = { nodes?: RawNode[]; edges?: RawEdge[] };

	type Props = {
		snapshots?: Record<string, Snapshot>;
		timeSteps?: number[];
		focusId?: string | null;
	};
	let { snapshots = {}, timeSteps = [], focusId = null }: Props = $props();

	type GenealogyNode = RawNode & { label: string; born: number; parentId: string | null; children: string[] };

	let lod = $state<'families' | 'branches' | 'languages'>('branches');
	let query = $state('');
	let focused = $state<string | null>(null);
	$effect(() => {
		if (focusId && focused === null) focused = focusId;
	});

	const allNodes = $derived.by(() => {
		const merged = new Map<string, GenealogyNode>();
		const years = [...timeSteps].sort((a, b) => a - b);
		for (const year of years) {
			for (const node of snapshots[String(year)]?.nodes ?? snapshots[year]?.nodes ?? []) {
				const existing = merged.get(node.id);
				const label = String(node.data?.label ?? node.data?.name ?? node.id);
				const born = Number(node.data?.year ?? year);
				if (!existing || born < existing.born) {
					merged.set(node.id, { ...node, label, born, parentId: existing?.parentId ?? null, children: existing?.children ?? [] });
				}
			}
		}
		// Older snapshots often contain no explicit parent field. Prefer an
		// inheritance edge when one exists, but never interpret a contact edge
		// as genealogy.
		for (const year of years) {
			for (const edge of snapshots[String(year)]?.edges ?? snapshots[year]?.edges ?? []) {
				const relation = edge.data?.relation ?? edge.data?.contactType;
				const isContact = edge.type === 'contact' && relation !== 'inheritance';
				if (isContact) continue;
				const child = merged.get(edge.target);
				if (child && merged.has(edge.source) && !child.parentId && edge.source !== edge.target) child.parentId = edge.source;
			}
		}
		for (const node of merged.values()) {
			if (node.parentId) merged.get(node.parentId)?.children.push(node.id);
		}
		return [...merged.values()].sort((a, b) => a.born - b.born || a.label.localeCompare(b.label));
	});

	const roots = $derived(allNodes.filter((node) => !node.parentId));
	const visibleNodes = $derived.by(() => {
		const needle = query.trim().toLocaleLowerCase();
		let result = allNodes;
		if (focused) {
			const ids = new Set<string>();
			const visit = (id: string) => { if (ids.has(id)) return; ids.add(id); allNodes.find((node) => node.id === id)?.children.forEach(visit); };
			visit(focused);
			result = result.filter((node) => ids.has(node.id) || node.id === focused);
		}
		if (needle) result = result.filter((node) => node.label.toLocaleLowerCase().includes(needle) || node.id.toLocaleLowerCase().includes(needle));
		if (lod === 'families') return roots;
		if (lod === 'branches') return result.filter((node) => node.children.length > 0 || !node.parentId);
		return result;
	});

	function childrenOf(node: GenealogyNode): GenealogyNode[] {
		return node.children.map((id) => allNodes.find((candidate) => candidate.id === id)).filter(Boolean) as GenealogyNode[];
	}

	function focusBranch(node: GenealogyNode) {
		focused = focused === node.id ? null : node.id;
	}

	function resetFocus() { focused = null; query = ''; }
</script>

<div class="flex min-h-[calc(100vh-2rem)] flex-col gap-4 p-4 md:p-6">
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div>
			<div class="mb-2 flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
				<GitBranch class="h-4 w-4" /> Genealogie
			</div>
			<h1 class="text-3xl font-semibold tracking-tight">Rodokmen jazyků</h1>
			<p class="mt-1 max-w-2xl text-sm text-muted-foreground">Read-only pohled na dědičnost. Mapa, kontakty a časová osa zůstávají oddělenými pohledy.</p>
		</div>
		<div class="flex gap-2">
			<Button variant="outline" size="sm" onclick={() => (lod = lod === 'families' ? 'branches' : 'families')}>
				{lod === 'families' ? 'Zobrazit větve' : 'Sbalit na rodiny'}
			</Button>
			<Button variant="ghost" size="sm" onclick={resetFocus} disabled={!focused && !query}>Resetovat fokus</Button>
		</div>
	</div>

	<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
		<Card class="min-w-0">
			<CardHeader class="border-b pb-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div><CardTitle>Hierarchický přehled</CardTitle><CardDescription>{visibleNodes.length} z {allNodes.length} uzlů · LOD: {lod}</CardDescription></div>
					<div class="flex items-center gap-1 rounded-lg border p-1" aria-label="Úroveň detailu">
						{#each ['families', 'branches', 'languages'] as option}
							<button class="rounded px-2 py-1 text-xs {lod === option ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'}" onclick={() => (lod = option as typeof lod)}>{option === 'families' ? 'Rodiny' : option === 'branches' ? 'Větve' : 'Jazyky'}</button>
						{/each}
					</div>
				</div>
				<label class="relative mt-3 block max-w-md">
					<Search class="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
					<input class="h-8 w-full rounded-md border bg-background pl-8 pr-2 text-sm outline-none focus:ring-2 focus:ring-ring" bind:value={query} placeholder="Najít jazyk nebo větev…" aria-label="Najít jazyk nebo větev" />
				</label>
			</CardHeader>
			<CardContent class="overflow-x-auto p-4">
				{#if allNodes.length === 0}
					<div class="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">Projekt zatím nemá žádné genealogické uzly. Po vytvoření protojazyka se objeví zde.</div>
				{:else}
					<div class="min-w-[42rem] space-y-5">
						{#each roots as root (root.id)}
							{@const rootVisible = visibleNodes.some((node) => node.id === root.id)}
							{#if rootVisible}
								<div class="rounded-lg border bg-muted/20 p-3">
									<button class="flex w-full items-center justify-between text-left" onclick={() => focusBranch(root)} aria-label="Zaměřit větev {root.label}">
										<span class="font-medium">{root.label}</span><span class="text-xs text-muted-foreground">od {root.born} · {root.children.length} větví</span>
									</button>
									{#if lod !== 'families'}
										<div class="mt-3 grid gap-2 border-l-2 pl-4 md:grid-cols-2">
											{#each childrenOf(root) as child (child.id)}
												{#if visibleNodes.some((node) => node.id === child.id)}
													<div class="rounded-md border bg-card p-2">
														<button class="w-full text-left" onclick={() => focusBranch(child)}><span class="font-medium">{child.label}</span><span class="ml-2 text-xs text-muted-foreground">{child.born}</span></button>
														{#if lod === 'languages' && child.children.length > 0}<div class="mt-2 flex flex-wrap gap-1">{#each childrenOf(child) as leaf (leaf.id)}<span class="rounded bg-muted px-2 py-0.5 text-xs">{leaf.label}</span>{/each}</div>{/if}
													</div>
												{/if}
											{/each}
										</div>
									{/if}
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>

		<aside class="space-y-4">
			<Card><CardHeader><CardTitle class="text-base">Fokus větve</CardTitle><CardDescription>Detail otevře samostatný jazykový pohled.</CardDescription></CardHeader><CardContent>{#if focused}<p class="text-sm font-medium">{allNodes.find((node) => node.id === focused)?.label ?? focused}</p><p class="mt-1 text-xs text-muted-foreground">{allNodes.find((node) => node.id === focused)?.children.length ?? 0} potomků</p><a class="mt-3 inline-block text-sm underline underline-offset-4" href={`/project/${encodeURIComponent($page.params.id ?? '')}/languages/${encodeURIComponent(focused)}`}>Otevřít detail jazyka</a>{:else}<p class="text-sm text-muted-foreground">Vyberte větev v hierarchii.</p>{/if}</CardContent></Card>
			<Card><CardHeader><CardTitle class="text-base">Kontrakt obrazovky</CardTitle></CardHeader><CardContent class="space-y-2 text-xs text-muted-foreground"><p>✓ Zobrazuje jen dědičnost a fokus.</p><p>✓ Kontakty nejsou genealogické hrany.</p><p>✓ Nezapisuje do projektu ani neupravuje snapshoty.</p><p>✓ Detail se načítá až po explicitním otevření.</p></CardContent></Card>
			<div class="flex items-center justify-end gap-1 text-xs text-muted-foreground"><ZoomOut class="h-3.5 w-3.5" /> LOD je řízený hierarchií <ZoomIn class="h-3.5 w-3.5" /></div>
		</aside>
	</div>
</div>
