<!-- Značka jazyka: jeho vlastní jméno (IPA) vyrostlé jako malá značka CEE, v barvě jazyka.
     Jméno se v čase mění, a se jménem i značka. -->
<script lang="ts">
	import { sigil } from './sigil';

	let { ipa, color = 'currentColor', size = 24, label }: { ipa: string; color?: string; size?: number; label?: string } = $props();
	const s = $derived(sigil(ipa));
</script>

<svg
	class="sigil"
	width={size}
	height={size}
	viewBox={s.view.join(' ') + ' ' + s.view[2]}
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}><path d={s.d} fill={color} /></svg
>

<style>
	.sigil {
		display: inline-block;
		flex: none;
		vertical-align: middle;
	}
</style>
