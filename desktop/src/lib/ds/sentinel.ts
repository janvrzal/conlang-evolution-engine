// Sentinel design systému: mimo src/lib/ds se nesmí stavět vlastní komponenty ani styl.
// Obrazovky skládají jen komponenty z `$lib/ds`. Výjimky jsou v src/lib/ds/allowlist.json.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';

export type Rule = 'import-component' | 'raw-element' | 'style';
export interface Violation {
	file: string;
	line: number;
	rule: Rule;
	detail: string;
}
export interface Exception {
	file: string;
	rule: Rule;
	/** konkrétní prvek nebo import; prázdné = celé pravidlo pro soubor */
	detail?: string;
	reason: string;
}

/** Ovládací a grafické prvky, které mají v ds vlastní komponentu. */
export const RAW_ELEMENTS = ['button', 'input', 'select', 'textarea', 'canvas', 'svg', 'table', 'dialog', 'progress', 'meter'] as const;

const lineOf = (text: string, index: number) => text.slice(0, index).split('\n').length;
/** Nahradí úsek mezerami se zachováním řádků, aby čísla řádků seděla. */
const blank = (s: string) => s.replace(/[^\n]/g, ' ');

/** Je import `.svelte` ve skutečnosti modul s runami (`x.svelte.ts`)? */
export type ModuleCheck = (spec: string, file: string) => boolean;

export function scanSource(file: string, source: string, isModule: ModuleCheck = () => false): Violation[] {
	const out: Violation[] = [];
	const isSvelte = file.endsWith('.svelte');
	// importy komponent: jen z indexu `$lib/ds`
	const importRe = /(?:import|export)\s[^;]*?from\s*['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g;
	for (const m of source.matchAll(importRe)) {
		const spec = m[1] ?? m[2];
		if (spec.endsWith('.svelte') && !isModule(spec, file)) out.push({ file, line: lineOf(source, m.index), rule: 'import-component', detail: spec });
		else if (/^(\$lib\/ds\/|\.\.?\/.*\bds\/)/.test(spec)) out.push({ file, line: lineOf(source, m.index), rule: 'import-component', detail: spec });
	}
	if (!isSvelte) return out;
	// značky: bez komentářů a skriptů
	let markup = source.replace(/<!--[\s\S]*?-->/g, blank).replace(/<script\b[\s\S]*?<\/script>/g, blank);
	for (const m of markup.matchAll(/<style\b/g)) out.push({ file, line: lineOf(markup, m.index), rule: 'style', detail: '<style>' });
	markup = markup.replace(/<style\b[\s\S]*?<\/style>/g, blank);
	for (const m of markup.matchAll(/\sstyle(:[\w-]+)?\s*=/g)) out.push({ file, line: lineOf(markup, m.index), rule: 'style', detail: `style${m[1] ?? ''}=` });
	for (const m of markup.matchAll(/\sclass:[\w-]+/g)) out.push({ file, line: lineOf(markup, m.index), rule: 'style', detail: m[0].trim() });
	for (const m of markup.matchAll(/\{@html\b/g)) out.push({ file, line: lineOf(markup, m.index), rule: 'raw-element', detail: '{@html}' });
	for (const m of markup.matchAll(/<([a-z][a-z0-9-]*)\b/g)) {
		const tag = m[1];
		if ((RAW_ELEMENTS as readonly string[]).includes(tag)) out.push({ file, line: lineOf(markup, m.index), rule: 'raw-element', detail: `<${tag}>` });
	}
	return out;
}

export function walk(dir: string): string[] {
	const out: string[] = [];
	for (const name of readdirSync(dir)) {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) out.push(...walk(path));
		else if (/\.(svelte|ts|js)$/.test(name) && !/\.test\.ts$/.test(name)) out.push(path);
	}
	return out;
}

/** Projde src/ (mimo src/lib/ds) a vrátí porušení, která allowlist nepovoluje. */
export function scanApp(srcDir: string, exceptions: Exception[]): { violations: Violation[]; unused: Exception[] } {
	const dsDir = join(srcDir, 'lib', 'ds') + sep;
	const used = new Set<Exception>();
	const violations: Violation[] = [];
	for (const path of walk(srcDir)) {
		if (path.startsWith(dsDir)) continue;
		const file = relative(srcDir, path).split(sep).join('/');
		const isModule: ModuleCheck = (spec) => {
			const base = spec.startsWith('$lib/') ? join(srcDir, 'lib', spec.slice(5)) : spec.startsWith('.') ? resolve(dirname(path), spec) : null;
			return !!base && (existsSync(`${base}.ts`) || existsSync(`${base}.js`));
		};
		for (const v of scanSource(file, readFileSync(path, 'utf8'), isModule)) {
			const ok = exceptions.find((e) => e.file === v.file && e.rule === v.rule && (!e.detail || e.detail === v.detail));
			if (ok) used.add(ok);
			else violations.push(v);
		}
	}
	return { violations, unused: exceptions.filter((e) => !used.has(e)) };
}
