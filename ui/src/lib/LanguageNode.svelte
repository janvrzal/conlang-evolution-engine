<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';
	import { Tree, TreePalm, Plant, Mountains, Sun, Waves, MapPin, Question, CastleTurret, Tent, House, Users } from 'phosphor-svelte';

	let { data, isConnectable } = $props<{
		data: { 
			label: string; 
			isProto?: boolean; 
			year?: number;
			biome?: string;
			society?: string;
			isDead?: boolean;
		};
		isConnectable: boolean;
	}>();

	let actuallyConnectable = $derived(isConnectable && !data.isDead);

	let showBiomePicker = $state(false);
	let showSocietyPicker = $state(false);

	const biomes = [
		{ id: 'forest', name: 'Les', icon: Tree },
		{ id: 'rainforest', name: 'Džungle', icon: TreePalm },
		{ id: 'steppe', name: 'Step', icon: Plant },
		{ id: 'mountains', name: 'Hory', icon: Mountains },
		{ id: 'desert', name: 'Poušť', icon: Sun },
		{ id: 'coast', name: 'Pobřeží', icon: Waves },
		{ id: 'island', name: 'Ostrov', icon: MapPin },
	];

	const societies = [
		{ id: 'hierarchic', name: 'Hierarchická', icon: CastleTurret },
		{ id: 'nomadic', name: 'Nomádi', icon: Tent },
		{ id: 'egalitarian', name: 'Rovnostářská', icon: House },
	];

	// Musí být kapitalizované: v Svelte se komponenta jako dynamická značka
	// (<X ... />) pozná podle velkého písmena, malé písmeno by se
	// interpretovalo jako obyčejný HTML tag beze smyslu.
	let CurrentBiomeIcon = $derived(biomes.find(b => b.id === data.biome)?.icon || Question);
	let CurrentSocietyIcon = $derived(societies.find(s => s.id === data.society)?.icon || Users);

	function setBiome(id: string) {
		data.biome = id;
		showBiomePicker = false;
	}

	function setSociety(id: string) {
		data.society = id;
		showSocietyPicker = false;
	}
</script>

<div class="w-12 h-12 rounded-full border-2 flex items-center justify-center {data.isDead ? 'border-muted-foreground bg-muted opacity-80 shadow-none' : data.isProto ? 'border-primary bg-primary/20 shadow-sm group-hover:border-foreground' : 'border-border bg-background shadow-sm group-hover:border-foreground'} transition-colors relative z-20 group">
	
	<!-- Skryté Handles pro spojení přesně do středu. Jsou umístěné bezpečně uprostřed standardním stylem. 
		     Pomocí ::after pseudo-elementu zvětšujeme neviditelný hitbox, aby se daly snáze trefit myší. -->
	<Handle 
		type="target" 
		position={Position.Top} 
		isConnectable={actuallyConnectable} 
		class="after:content-[''] after:absolute after:-top-[26px] after:-left-[26px] after:-right-[26px] after:-bottom-[26px] after:rounded-full after:cursor-crosshair"
		style="top: 50%; left: 50%; width: 1px; height: 1px; min-width: 0; min-height: 0; opacity: 0; border: none; background: transparent;"
	/>
	<Handle 
		type="source" 
		position={Position.Bottom} 
		isConnectable={actuallyConnectable} 
		class="after:content-[''] after:absolute after:-top-[26px] after:-left-[26px] after:-right-[26px] after:-bottom-[26px] after:rounded-full after:cursor-crosshair"
		style="top: 50%; left: 50%; width: 1px; height: 1px; min-width: 0; min-height: 0; opacity: 0; border: none; background: transparent;"
	/>

	<!-- Texty vně kolečka (dole) -->
	<div class="absolute top-14 left-1/2 -translate-x-1/2 text-center pointer-events-none w-48 z-10">
		<h3 class="font-bold text-[13px] tracking-tight leading-tight {data.isDead ? 'text-muted-foreground line-through bg-muted/70' : 'text-foreground bg-background/70'} backdrop-blur-sm rounded-md px-1 py-0.5 inline-block">
			{data.label}
		</h3>
		{#if data.year !== undefined}
			<br/><p class="text-[10px] text-muted-foreground uppercase font-semibold mt-0.5 bg-background/70 backdrop-blur-sm rounded-md px-1 inline-block">Rok {data.year}</p>
		{/if}
	</div>

	<!-- Ikona Společnosti (vlevo nahoře) -->
	<div class="absolute -top-1 -left-4 z-30 pointer-events-auto">
		<button class="bg-card text-foreground border rounded-full p-1 shadow-sm hover:bg-muted transition-colors relative {data.society ? 'border-primary text-primary' : 'opacity-50 group-hover:opacity-100'}" onclick={() => { showSocietyPicker = !showSocietyPicker; showBiomePicker = false; }}>
			<CurrentSocietyIcon size={14} weight={data.society ? 'fill' : 'regular'} />
		</button>
		{#if showSocietyPicker}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="absolute top-8 -left-4 bg-popover text-popover-foreground border rounded-md shadow-lg p-1 flex flex-col gap-1 w-32 animate-in fade-in zoom-in duration-150" onclick={(e) => e.stopPropagation()}>
				<div class="text-[10px] uppercase font-bold text-muted-foreground px-2 pt-1">Společnost</div>
				{#each societies as s (s.id)}
					{@const Icon = s.icon}
					<button class="flex items-center gap-2 text-xs p-1.5 hover:bg-muted rounded text-left {data.society === s.id ? 'bg-primary/10 text-primary' : ''}" onclick={() => setSociety(s.id)}>
						<Icon size={14} weight={data.society === s.id ? 'fill' : 'regular'} />
						{s.name}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Ikona Biomu (vpravo nahoře) -->
	<div class="absolute -top-1 -right-4 z-30 pointer-events-auto">
		<button class="bg-card text-foreground border rounded-full p-1 shadow-sm hover:bg-muted transition-colors relative {data.biome ? 'border-primary text-primary' : 'opacity-50 group-hover:opacity-100'}" onclick={() => { showBiomePicker = !showBiomePicker; showSocietyPicker = false; }}>
			<CurrentBiomeIcon size={14} weight={data.biome ? 'fill' : 'regular'} />
		</button>
		{#if showBiomePicker}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="absolute top-8 -right-4 bg-popover text-popover-foreground border rounded-md shadow-lg p-1 flex flex-col gap-1 w-32 animate-in fade-in zoom-in duration-150" onclick={(e) => e.stopPropagation()}>
				<div class="text-[10px] uppercase font-bold text-muted-foreground px-2 pt-1">Biom</div>
				{#each biomes as b (b.id)}
					{@const Icon = b.icon}
					<button class="flex items-center gap-2 text-xs p-1.5 hover:bg-muted rounded text-left {data.biome === b.id ? 'bg-primary/10 text-primary' : ''}" onclick={() => setBiome(b.id)}>
						<Icon size={14} weight={data.biome === b.id ? 'fill' : 'regular'} />
						{b.name}
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>
