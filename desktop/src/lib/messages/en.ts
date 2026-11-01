// English message catalogue. Keys must match cs.ts (checked by the type).
import type cs from './cs';

const s = (n: number | string, one: string, many: string) => (Number(n) === 1 ? one : many);

const en: Record<keyof typeof cs, string | ((p: Record<string, string | number>) => string)> = {
	'app.name': 'CEE',
	'app.tagline': 'Languages evolving through time and landscape',
	'locale.switch': 'Interface language',

	'step.world': 'World',
	'step.proto': 'Proto-language',
	'step.history': 'History',
	'step.results': 'Results',
	'step.branches': 'Branches',
	'step.nav': 'Workflow',

	'engine.connecting': 'Connecting to the engine…',
	'engine.ready': 'Engine ready',
	'engine.offline': 'Engine not running',
	'engine.outdated': 'The engine is outdated (revision {have}, needs {need}). Restart it.',
	'engine.hint': 'Start the engine with cee ui, or launch the app through Tauri, which starts it for you.',
	'engine.retry': 'Try again',

	'project.untitled': 'New world',
	'project.open': 'Open…',
	'project.save': 'Save',
	'project.starter': 'Sample world',
	'project.saved': 'Saved',
	'project.unsaved': 'Unsaved changes',
	'project.opened': 'Opened: {name}',
	'project.bad_file': 'This file is not a CEE world description.',
	'project.years': (p) => `${p.years} years`,

	'check.title': 'Check',
	'check.ok': 'The world is fine.',
	'check.running': 'Checking…',
	'check.engine_language':
		'Engine messages are Czech for now; translation arrives with error codes in the engine.',

	'run.start': (p) => `Run ${p.years} years`,
	'run.cancel': 'Stop',
	'run.progress': (p) => `Year ${p.year} of ${p.end}`,
	'run.done': (p) => `Done in ${p.seconds} s`,
	'run.failed': 'The run failed',
	'run.cancelled': 'Run stopped',
	'run.none': 'The world has not run yet. Start it with the button below.',

	'world.regions': 'Regions',
	'world.region': 'Region',
	'world.language': 'Starting language',
	'world.terrain': 'Terrain',
	'world.identity': 'Identity',
	'world.villages': 'Villages',
	'world.neighbours': 'Neighbours',
	'world.editor_soon': 'The map editor from the prototype comes in the next step.',

	'terrain.plain': 'plain',
	'terrain.hills': 'hills',
	'terrain.mountains': 'mountains',
	'terrain.island': 'island',
	'identity.shared': 'shared',
	'identity.distinct': 'distinct',
	'identity.strong': 'strong',

	'proto.languages': 'Proto-languages',
	'proto.consonants': 'Consonants',
	'proto.vowels': 'Vowels',
	'proto.default_inventory': 'default',
	'proto.stress': 'Stress',
	'proto.grammar': 'Grammar',
	'proto.words': (p) => `${p.n} ${s(p.n, 'own word', 'own words')}`,

	'history.events': 'Events',
	'history.year': 'Year',
	'history.kind': 'Event',
	'history.detail': 'Details',
	'history.none': 'No events.',

	'results.languages': 'Languages',
	'results.dialects': 'Dialects',
	'results.endonym': 'speakers call it',
	'results.villages': (p) => `${p.n} ${s(p.n, 'village', 'villages')}`,
	'results.speakers': (p) => `${p.n} speakers`,
	'results.extinct': (p) => `extinct ${p.year}`,
	'results.born': (p) => `since ${p.year}`,
	'results.from_parent': (p) => `split from ${p.parent}`,

	'branches.soon': 'Comparing branches of history from the prototype comes later.',

	'kind.state': 'State founded',
	'kind.language_policy': 'Language policy',
	'kind.annexation': 'Annexation',
	'kind.secession': 'Secession',
	'kind.collapse': 'State collapse',
	'kind.border_policy': 'Border',
	'kind.lingua_franca': 'Lingua franca',
	'kind.standard': 'Written standard',
	'kind.schools': 'Schools',
	'kind.revival': 'Revival',
	'kind.preserve': 'Language protection',
	'kind.identity': 'Regional identity',
	'kind.immigration': 'Incoming strangers'
};

export default en;
