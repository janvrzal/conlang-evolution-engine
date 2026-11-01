// Zkopíruje úplné písmo Charis 7 (SIL, OFL) do static/fonts pro zápis IPA.
// Balík stáhni z https://software.sil.org/charis/ a nastav CEE_CHARIS na jeho složku web.
import fs from 'node:fs';
import path from 'node:path';

const source = process.env.CEE_CHARIS;
if (!source) {
	console.error('Nastav CEE_CHARIS na složku web z balíku Charis 7.');
	process.exit(1);
}
const target = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'static', 'fonts');
fs.mkdirSync(target, { recursive: true });
for (const name of ['Charis-Regular.woff2', 'Charis-Italic.woff2', 'Charis-Bold.woff2']) {
	fs.copyFileSync(path.join(source, name), path.join(target, name));
	console.log(`static/fonts/${name}`);
}
