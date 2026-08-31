<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import { Select } from '$lib/components/ui/select';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import { Search, Tags, Type, Volume2 } from 'lucide-svelte';

	export type LanguageWord = {
		id: string;
		concept_id: string;
		to: string;
		from: string;
		polysemy?: string[];
		frequency?: number;
		active?: boolean;
		origin_type?: string;
		is_grammatical?: boolean;
		grammatical_features?: Record<string, string>;
	};

	let { words = [], onTrace }: { words?: LanguageWord[]; onTrace?: (word: LanguageWord) => void } = $props();
	let query = $state('');
	let grouping = $state<'concept' | 'form'>('concept');
	let register = $state('all');
	let community = $state('all');
	let lexicalClass = $state('all');

	const registers = $derived([
		...new Set(words.map((word) => word.grammatical_features?.['lexical.register']).filter(Boolean))
	].sort());
	const communities = $derived([
		...new Set(words.map((word) => word.grammatical_features?.['social.group']).filter(Boolean))
	].sort());
	const classes = $derived([
		...new Set(words.map((word) => word.grammatical_features?.['lexical.class']).filter(Boolean))
	].sort());
	const homonyms = $derived.by(() => {
		const forms = new Map<string, Set<string>>();
		for (const word of words) forms.set(word.to, new Set([...(forms.get(word.to) ?? []), word.concept_id]));
		return new Set([...forms].filter(([, concepts]) => concepts.size > 1).map(([form]) => form));
	});
	const filtered = $derived(
		words.filter((word) => {
			const q = query.trim().toLowerCase();
			const features = word.grammatical_features ?? {};
			return (
				(!q || `${word.to} ${word.concept_id} ${(word.polysemy ?? []).join(' ')}`.toLowerCase().includes(q)) &&
				(register === 'all' || features['lexical.register'] === register) &&
				(community === 'all' || features['social.group'] === community) &&
				(lexicalClass === 'all' || features['lexical.class'] === lexicalClass)
			);
		})
	);
	const groups = $derived.by(() => {
		const grouped = new Map<string, LanguageWord[]>();
		for (const word of filtered) {
			const key = grouping === 'concept' ? word.concept_id : word.to;
			grouped.set(key, [...(grouped.get(key) ?? []), word]);
		}
		return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right));
	});

	function flags(word: LanguageWord): string[] {
		const result: string[] = [];
		if (homonyms.has(word.to)) result.push('homonymum');
		if (words.filter((item) => item.concept_id === word.concept_id).length > 1) result.push('synonymum');
		const registerName = word.grammatical_features?.['lexical.register'];
		if (registerName && registerName !== 'neutral' && registerName !== 'ordinary') result.push(registerName);
		if (word.origin_type && word.origin_type !== 'inherited') result.push(word.origin_type);
		return result;
	}
</script>

<Card class="min-h-0">
	<CardHeader class="gap-3">
		<div class="flex items-center justify-between gap-3">
			<CardTitle class="flex items-center gap-2"><Volume2 size={18} /> Slovník</CardTitle>
			<span class="text-xs text-muted-foreground">{filtered.length} / {words.length}</span>
		</div>
		<div class="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
			<div class="relative md:col-span-2"><Search class="absolute left-3 top-2.5 text-muted-foreground" size={15} /><Input class="pl-9" bind:value={query} placeholder="Hledat formu, koncept nebo význam" /></div>
			<Select bind:value={grouping}><option value="concept">Podle konceptu</option><option value="form">Podle formy</option></Select>
			<Select bind:value={register}><option value="all">Všechny registry</option>{#each registers as item}<option value={item}>{item}</option>{/each}</Select>
			<Select bind:value={community}><option value="all">Všechny komunity</option>{#each communities as item}<option value={item}>{item}</option>{/each}</Select>
		</div>
		<div class="flex gap-2"><Select class="max-w-52" bind:value={lexicalClass}><option value="all">Všechny třídy slov</option>{#each classes as item}<option value={item}>{item}</option>{/each}</Select><span class="text-xs text-muted-foreground self-center">Homonyma a synonyma se počítají z celého řezu v daném roce.</span></div>
	</CardHeader>
	<CardContent class="space-y-4">
		{#each groups as [key, items]}
			<section class="rounded-lg border">
				<header class="flex items-center gap-2 border-b bg-muted/40 px-3 py-2"><Tags size={14} /><strong class="text-sm">{key}</strong><span class="text-xs text-muted-foreground">{items.length} {items.length === 1 ? 'lexém' : 'lexémy'}</span></header>
				<Table><TableHeader><TableRow><TableHead>Slovo</TableHead><TableHead>{grouping === 'concept' ? 'Významy' : 'Koncept'}</TableHead><TableHead>Užití a historie</TableHead><TableHead class="w-24"></TableHead></TableRow></TableHeader><TableBody>
					{#each items as word (word.id)}
						<TableRow><TableCell><div class="font-medium text-base">{word.to}</div>{#if word.from !== word.to}<div class="text-xs text-muted-foreground">z {word.from}</div>{/if}</TableCell><TableCell><div>{word.concept_id}</div>{#if word.polysemy?.length}<div class="text-xs text-muted-foreground">{word.polysemy.join(' · ')}</div>{/if}</TableCell><TableCell><div class="flex flex-wrap gap-1">{#each flags(word) as flag}<span class="rounded-full bg-muted px-2 py-0.5 text-[11px]">{flag}</span>{/each}{#if !flags(word).length}<span class="text-xs text-muted-foreground">běžné užití</span>{/if}</div></TableCell><TableCell>{#if onTrace}<Button variant="ghost" size="sm" onclick={() => onTrace?.(word)}><Type size={14} /> Historie</Button>{/if}</TableCell></TableRow>
					{/each}
				</TableBody></Table>
			</section>
		{:else}
			<div class="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">Žádný lexém neodpovídá zvoleným filtrům.</div>
		{/each}
	</CardContent>
</Card>
