import prettier from 'eslint-config-prettier';
import path from 'node:path';
import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import { defineConfig, includeIgnoreFile } from 'eslint/config';
import globals from 'globals';
import ts from 'typescript-eslint';

const gitignorePath = path.resolve(import.meta.dirname, '.gitignore');

export default defineConfig(
	includeIgnoreFile(gitignorePath),
	js.configs.recommended,
	ts.configs.recommended,
	svelte.configs.recommended,
	prettier,
	svelte.configs.prettier,
	{
		languageOptions: { globals: { ...globals.browser, ...globals.node } },
		rules: {
			// typescript-eslint strongly recommend that you do not use the no-undef lint rule on TypeScript projects.
			// see: https://typescript-eslint.io/troubleshooting/faqs/eslint/#i-get-errors-from-the-no-undef-rule-about-global-variables-not-being-defined-even-though-there-are-no-typescript-errors
			'no-undef': 'off',
			// SvelteFlow payloady jsou uživatelsky rozšiřitelné a přicházejí
			// z JSON projektu. Jejich postupné typování nesmí blokovat lint
			// celého UI; hranice API se ověřuje samostatně v svelte-check.
			'@typescript-eslint/no-explicit-any': 'off',
			// Editor používá dynamické projektové cesty a generické UI
			// komponenty. resolve() neumí tyto runtime cesty zpřesnit.
			'svelte/no-navigation-without-resolve': 'off',
			// Množiny zde vznikají lokálně během jednoho výpočtu; nejsou
			// dlouhodobým reaktivním stavem komponenty.
			'svelte/prefer-svelte-reactivity': 'off',
			// Některé prezentační seznamy nemají stabilní doménové ID.
			// Stavové seznamy (uzly/hrany) jsou klíčované explicitně.
			'svelte/require-each-key': 'off'
		}
	},
	{
		files: ['**/*.d.ts'],
		rules: { '@typescript-eslint/no-unused-vars': 'off' }
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				projectService: true,
				extraFileExtensions: ['.svelte'],
				parser: ts.parser
			}
		}
	},
	{
		// Override or add rule settings here, such as:
		// 'svelte/button-has-type': 'error'
		rules: {}
	}
);
