<!-- Výslovnost v IPA písmem Charis. size: s = v textu, m = tabulka, l = nadpis/vrt. -->
<script lang="ts">
	let {
		text,
		size = 's',
		tone,
		slashes = false,
		italic = false
	}: { text: string; size?: 's' | 'm' | 'l'; tone?: 'red' | 'muted'; slashes?: boolean; /** kurzíva: slovo z jiné rodiny */ italic?: boolean } = $props();
</script>

<span class="ipa {size} {tone ?? ''}" class:italic>{slashes ? `/${text}/` : text}</span>

<style>
	.ipa {
		font-family: var(--f-ipa);
		font-style: normal;
	}
	.m {
		font-size: 17px;
	}
	.l {
		font-size: 22px;
	}
	.italic {
		font-style: italic;
	}
	.red {
		color: var(--red);
	}
	.muted {
		color: var(--ink-2);
	}
</style>
