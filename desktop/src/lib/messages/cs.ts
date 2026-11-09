// Český katalog popisků. Klíče jsou společné s en.ts.
import { plural } from '../plural';
import * as s_projekty from './screens/projekty';
import * as s_svet from './screens/svet';
import * as s_protojazyky from './screens/protojazyky';
import * as s_pojmy from './screens/pojmy';
import * as s_dejiny from './screens/dejiny';
import * as s_model from './screens/model';
import * as s_atlas from './screens/atlas';
import * as s_jazyky from './screens/jazyky';
import * as s_slova from './screens/slova';
import * as s_kronika from './screens/kronika';
import * as s_cokdyby from './screens/cokdyby';
import * as s_shell from './screens/shell';

const core = {
	'app.name': 'CEE',
	'app.tagline': 'Vývoj jazyků v čase a krajině',
	'locale.switch': 'Jazyk rozhraní',

	'step.world': 'Svět',
	'step.proto': 'Protojazyk',
	'step.history': 'Dějiny',
	'step.results': 'Výsledky',
	'step.branches': 'Větve',
	'step.nav': 'Postup práce',

	'engine.connecting': 'Připojuji engine…',
	'engine.ready': 'Engine připraven',
	'engine.offline': 'Engine neběží',
	'engine.outdated': 'Engine je zastaralý (revize {have}, potřeba {need}). Restartuj ho.',
	'engine.hint': 'Spusť engine příkazem cee ui, nebo aplikaci přes Tauri, která ho spustí sama.',
	'engine.retry': 'Zkusit znovu',

	'project.untitled': 'Nový svět',
	'project.open': 'Otevřít…',
	'project.save': 'Uložit',
	'project.starter': 'Ukázkový svět',
	'project.saved': 'Uloženo',
	'project.unsaved': 'Neuložené změny',
	'project.opened': 'Otevřeno: {name}',
	'project.bad_file': 'Soubor není popis světa CEE.',
	'project.years': (p) => `${p.years} let`,

	'check.title': 'Kontrola',
	'check.ok': 'Svět je v pořádku.',
	'check.running': 'Kontroluji…',
	'check.engine_language':
		'Hlášení enginu jsou zatím jen česky; překlad přijde s kódy chyb v enginu.',

	'run.start': (p) => `Spustit ${p.years} let`,
	'run.cancel': 'Zastavit',
	'run.progress': (p) => `Rok ${p.year} z ${p.end}`,
	'run.done': (p) => `Hotovo za ${p.seconds} s`,
	'run.failed': 'Běh selhal',
	'run.cancelled': 'Běh zastaven',
	'run.none': 'Svět zatím neběžel. Spusť ho tlačítkem dole.',

	'world.regions': 'Kraje',
	'world.region': 'Kraj',
	'world.language': 'Jazyk na počátku',
	'world.terrain': 'Krajina',
	'world.identity': 'Svébytnost',
	'world.villages': 'Vesnic',
	'world.neighbours': 'Sousedé',
	'world.editor_soon': 'Editor mapy z prototypu sem přijde v dalším kroku.',

	'terrain.plain': 'rovina',
	'terrain.hills': 'pahorkatina',
	'terrain.mountains': 'hory',
	'terrain.island': 'ostrov',
	'identity.shared': 'sdílená',
	'identity.distinct': 'svébytná',
	'identity.strong': 'silná',

	'proto.languages': 'Protojazyky',
	'proto.consonants': 'Souhlásky',
	'proto.vowels': 'Samohlásky',
	'proto.default_inventory': 'výchozí',
	'proto.stress': 'Přízvuk',
	'proto.grammar': 'Mluvnice',
	'proto.words': (p) => `${p.n} ${plural(Number(p.n), 'vlastní slovo', 'vlastní slova', 'vlastních slov')}`,

	'history.events': 'Události',
	'history.year': 'Rok',
	'history.kind': 'Událost',
	'history.detail': 'Podrobnosti',
	'history.none': 'Žádné události.',

	'results.languages': 'Jazyky',
	'results.dialects': 'Nářečí',
	'results.endonym': 'sami říkají',
	'results.villages': (p) => `${p.n} ${plural(Number(p.n), 'ves', 'vsi', 'vsí')}`,
	'results.speakers': (p) => `${p.n} mluvčích`,
	'results.extinct': (p) => `vymřel ${p.year}`,
	'results.born': (p) => `od roku ${p.year}`,
	'results.from_parent': (p) => `odštěpil se od jazyka ${p.parent}`,

	'branches.soon': 'Porovnání větví dějin z prototypu sem přijde později.',

	'kind.state': 'Vznik státu',
	'kind.language_policy': 'Jazyková politika',
	'kind.annexation': 'Připojení krajů',
	'kind.secession': 'Odtržení',
	'kind.collapse': 'Zánik státu',
	'kind.border_policy': 'Hranice',
	'kind.lingua_franca': 'Lingua franca',
	'kind.standard': 'Spisovná norma',
	'kind.schools': 'Školy',
	'kind.revival': 'Obrození',
	'kind.preserve': 'Ochrana jazyka',
	'kind.identity': 'Svébytnost kraje',
	'kind.immigration': 'Příchod cizinců'
} satisfies Record<string, string | ((p: Record<string, string | number>) => string)>;

const cs = {
	...core,
	...s_projekty.cs,
	...s_svet.cs,
	...s_protojazyky.cs,
	...s_pojmy.cs,
	...s_dejiny.cs,
	...s_model.cs,
	...s_atlas.cs,
	...s_jazyky.cs,
	...s_slova.cs,
	...s_kronika.cs,
	...s_cokdyby.cs,
	...s_shell.cs,
};

export default cs;
