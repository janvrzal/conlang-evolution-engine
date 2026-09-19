<script lang="ts">
	import { Button } from '$lib/components/ui/button';

	let { timeSteps, currentIndex, onChange, onAdd } = $props<{
		timeSteps: number[];
		currentIndex: number;
		onChange: (index: number) => void;
		onAdd: () => void;
	}>();

	let minYear = $derived(Math.min(...timeSteps));
	let maxYear = $derived(Math.max(...timeSteps, minYear + 1));
	let span = $derived(maxYear - minYear || 1);
</script>

<div class="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 w-full max-w-2xl">
	<div
		class="bg-card/80 backdrop-blur-md rounded-full border shadow-sm px-8 py-3 flex items-center justify-between gap-4"
	>
		<div class="text-sm font-medium w-16 text-right whitespace-nowrap">
			Rok {timeSteps[currentIndex]}
		</div>
		<div class="relative flex-1 h-2 bg-muted rounded-full">
			<div
				class="absolute top-0 left-0 h-full bg-primary rounded-full transition-all duration-300"
				style="width: {((timeSteps[currentIndex] - minYear) / span) * 100}%"
			></div>
			{#each timeSteps as year, index}
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<div
					class="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 cursor-pointer transition-all hover:scale-125 {index ===
					currentIndex
						? 'bg-primary border-background shadow-sm scale-110'
						: 'bg-background border-primary/50'}"
					style="left: calc({((year - minYear) / span) * 100}% - 8px)"
					onclick={() => onChange(index)}
					title="Rok {year}"
				></div>
			{/each}
		</div>
		<Button
			variant="ghost"
			size="sm"
			class="h-8 w-8 p-0 rounded-full shrink-0"
			onclick={onAdd}
			title="Přidat bod na osu">+</Button
		>
	</div>
</div>
