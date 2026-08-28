<script lang="ts">
	import { BaseEdge, EdgeLabel, getStraightPath, type EdgeProps } from '@xyflow/svelte';
	import { Sword, Scales, Sparkle, UsersThree, Question, ArrowsLeftRight, ArrowRight, ArrowLeft } from 'phosphor-svelte';

	type ContactEdgeData = {
		contactType?: string;
		intensity?: number;
		direction?: 'ab' | 'ba' | 'both';
	};

	type $$Props = EdgeProps & { data?: ContactEdgeData };
	
	let {
		id,
		sourceX,
		sourceY,
		targetX,
		targetY,
		style,
		markerEnd,
		markerStart,
		data = {}
	}: $$Props = $props();

	let intensity = $derived(data.intensity ?? 50);
	let contactType = $derived(data.contactType ?? 'neighborhood');
	let direction = $derived(data.direction ?? 'ab');

	let showPicker = $state(false);

	const contactTypes = [
		{ id: 'war', name: 'Válka', icon: Sword },
		{ id: 'trade', name: 'Obchod', icon: Scales },
		{ id: 'religion', name: 'Náboženství', icon: Sparkle },
		{ id: 'neighborhood', name: 'Sousedství', icon: UsersThree }
	];

	let path = $derived(getStraightPath({ sourceX, sourceY, targetX, targetY }));
	let labelX = $derived(path[1]);
	let labelY = $derived(path[2]);
	
	let currentIcon = $derived(contactTypes.find(c => c.id === contactType)?.icon || Question);

	// Mutace Svelte 5 objektů napřímo updatuje state SvelteFlow
	function setType(typeId: string) {
		data.contactType = typeId;
	}
	
	function setDirection(dir: 'ab' | 'ba' | 'both') {
		data.direction = dir;
	}
	
	function updateIntensity(val: number) {
		data.intensity = val;
	}
</script>

<!--
	`style` je ten samý obecný vzhled, který dostává KAŽDÁ hrana
	(`defaultEdgeOptions.style` v map/+page.svelte) — kdyby se předal
	beze změny, kontakt by se vizuálně nelišil od dědičnosti a jediný
	rozdíl by byl malý odznáček uprostřed, snadno přehlédnutelný.
	Kontakt proto dostává vlastní barvu a přerušovanou čáru navrch.
-->
<BaseEdge path={path[0]} style="{style}; stroke: var(--contact-edge-stroke, #6366f1); stroke-width: 1.8; stroke-dasharray: 6 4; opacity: 0.85;" {markerEnd} {markerStart} />

<foreignObject
	width={250}
	height={250}
	x={labelX - 125}
	y={labelY - 125}
	class="edgebutton-foreignobject overflow-visible pointer-events-none z-50"
	requiredExtensions="http://www.w3.org/1999/xhtml"
>
	<div class="flex items-center justify-center w-full h-full pointer-events-none">
		<div class="relative pointer-events-auto">
			<button class="bg-card text-foreground border rounded-full p-1.5 shadow-md hover:bg-muted transition-colors {contactType ? 'border-primary text-primary' : ''}" onclick={() => showPicker = !showPicker}>
				{#if currentIcon}
					{@const Icon = currentIcon}
					<Icon size={16} weight="fill" />
				{/if}
			</button>

			{#if showPicker}
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div class="absolute top-10 left-1/2 -translate-x-1/2 bg-popover text-popover-foreground border rounded-lg shadow-xl p-3 flex flex-col gap-4 w-56 animate-in fade-in zoom-in duration-150 z-[100]" onclick={(e) => e.stopPropagation()}>
					
					<!-- Typ Kontaktu -->
					<div>
						<div class="text-[10px] uppercase font-bold text-muted-foreground px-1 pb-1">Typ Kontaktu</div>
						<div class="grid grid-cols-2 gap-1.5">
							{#each contactTypes as c}
								{@const Icon = c.icon}
								<button class="flex items-center gap-1.5 text-xs p-1.5 hover:bg-muted rounded text-left border border-transparent transition-colors {contactType === c.id ? 'bg-primary/10 text-primary border-primary/30 font-medium' : ''}" onclick={() => setType(c.id)}>
									<Icon size={14} weight={contactType === c.id ? 'fill' : 'regular'} />
									<span class="truncate">{c.name}</span>
								</button>
							{/each}
						</div>
					</div>

					<!-- Směr -->
					<div>
						<div class="text-[10px] uppercase font-bold text-muted-foreground px-1 pb-1">Směr vlivu</div>
						<div class="flex gap-1 justify-between bg-muted/50 p-1 rounded-md border">
							<button class="flex-1 flex justify-center p-1.5 rounded hover:bg-background border border-transparent transition-all {direction === 'ba' ? 'bg-background shadow-sm text-primary border-border' : ''}" onclick={() => setDirection('ba')} title="Cíl ovlivňuje zdroj (B -> A)">
								<ArrowLeft size={16} weight="bold" />
							</button>
							<button class="flex-1 flex justify-center p-1.5 rounded hover:bg-background border border-transparent transition-all {direction === 'both' ? 'bg-background shadow-sm text-primary border-border' : ''}" onclick={() => setDirection('both')} title="Obousměrně (A <-> B)">
								<ArrowsLeftRight size={16} weight="bold" />
							</button>
							<button class="flex-1 flex justify-center p-1.5 rounded hover:bg-background border border-transparent transition-all {direction === 'ab' ? 'bg-background shadow-sm text-primary border-border' : ''}" onclick={() => setDirection('ab')} title="Zdroj ovlivňuje cíl (A -> B)">
								<ArrowRight size={16} weight="bold" />
							</button>
						</div>
					</div>

					<!-- Intenzita -->
					<div>
						<div class="flex justify-between items-center px-1 pb-1.5">
							<div class="text-[10px] uppercase font-bold text-muted-foreground">Intenzita vlivu</div>
							<div class="text-xs font-mono text-primary font-bold">{intensity}%</div>
						</div>
						<div class="px-1">
							<input type="range" min="0" max="100" value={intensity} oninput={(e) => updateIntensity(parseInt(e.currentTarget.value))} class="w-full accent-primary h-2 bg-muted/80 rounded-lg appearance-none cursor-pointer border" />
						</div>
					</div>
					
					<div class="flex justify-end pt-1">
						<button class="text-[11px] uppercase font-bold bg-muted text-foreground px-3 py-1.5 rounded hover:bg-primary hover:text-primary-foreground transition-colors" onclick={() => showPicker = false}>Zavřít</button>
					</div>
				</div>
			{/if}
		</div>
	</div>
</foreignObject>
