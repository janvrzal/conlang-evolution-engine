// Spouští se v `npm test` a samostatně `npm run check:ds`.
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { scanApp, scanSource, type Exception } from './sentinel';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..', '..');
const allow = JSON.parse(readFileSync(join(here, 'allowlist.json'), 'utf8')) as { exceptions: Exception[] };

describe('sentinel design systému', () => {
	it('obrazovky používají jen komponenty z $lib/ds', () => {
		const { violations } = scanApp(src, allow.exceptions);
		const report = violations.map((v) => `${v.file}:${v.line} ${v.rule} ${v.detail}`).join('\n');
		expect(report, 'Mimo src/lib/ds je vlastní komponenta, prvek nebo styl. Použij komponentu z $lib/ds; chybí-li, řekni správci ds (výjimka jen přes allowlist.json).').toBe('');
	});

	it('každá výjimka má důvod a pořád něco povoluje', () => {
		for (const e of allow.exceptions) expect(e.reason?.trim(), `${e.file}: výjimka bez důvodu`).toBeTruthy();
		const { unused } = scanApp(src, allow.exceptions);
		expect(unused.map((e) => `${e.file} ${e.rule} ${e.detail ?? ''}`)).toEqual([]);
	});

	it('každá komponenta ds je v indexu', () => {
		const index = readFileSync(join(here, 'index.ts'), 'utf8');
		const missing = readdirSync(here).filter((n) => n.endsWith('.svelte') && !index.includes(`./${n}'`));
		expect(missing).toEqual([]);
	});

	it('pozná zakázané vzory', () => {
		const found = scanSource(
			'routes/x/+page.svelte',
			`<script lang="ts">import Foo from './Foo.svelte'; import { Button } from '$lib/ds'; import Bar from '$lib/ds/Bar.svelte';</script>
<!-- <button> v komentáři nevadí -->
<div style="color:red" class:on={x}><button>a</button><Button>b</Button><svg></svg>{@html y}</div>
<style>div{}</style>`
		);
		expect(found.map((v) => `${v.rule} ${v.detail}`)).toEqual([
			'import-component ./Foo.svelte',
			'import-component $lib/ds/Bar.svelte',
			'style <style>',
			'style style=',
			'style class:on',
			'raw-element {@html}',
			'raw-element <button>',
			'raw-element <svg>'
		]);
	});
});
