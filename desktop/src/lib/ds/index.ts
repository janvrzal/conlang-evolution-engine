// Design systém CEE. Obrazovky (src/routes) smí používat jen komponenty odsud;
// hlídá to src/lib/ds/sentinel.test.ts, výjimky jsou v allowlist.json.

// kostra a rozvržení
export { default as Shell } from './Shell.svelte';
export { default as AppBar, type NavItem } from './AppBar.svelte';
export { default as Screen } from './Screen.svelte';
export { default as Area } from './Area.svelte';
export { default as Card } from './Card.svelte';
export { default as Stack } from './Stack.svelte';
export { default as Cluster } from './Cluster.svelte';
export { default as Spacer } from './Spacer.svelte';
export { default as Stage } from './Stage.svelte';
export { default as Floating } from './Floating.svelte';
export { default as Footer } from './Footer.svelte';

// text a drobnosti
export { default as Text } from './Text.svelte';
export { default as Ipa } from './Ipa.svelte';
export { default as Term } from './Term.svelte';
export { default as Kbd } from './Kbd.svelte';
export { default as Swatch } from './Swatch.svelte';
export { default as Icon, type IconName } from './Icon.svelte';

// ovládání
export { default as Button } from './Button.svelte';
export { default as Segmented } from './Segmented.svelte';
export { default as Tabs } from './Tabs.svelte';
export { default as Field } from './Field.svelte';
export { default as TextInput } from './TextInput.svelte';
export { default as Checkbox } from './Checkbox.svelte';
export { default as Range } from './Range.svelte';
export { default as Select } from './Select.svelte';
export { default as FilePicker } from './FilePicker.svelte';
export { default as Chip } from './Chip.svelte';
export { default as ParamRow } from './ParamRow.svelte';

// data
export { default as Ledger } from './Ledger.svelte';
export { default as LedgerRow } from './LedgerRow.svelte';
export { default as Bars, type BarRow } from './Bars.svelte';
export { default as Table } from './Table.svelte';
export { default as Tr } from './Tr.svelte';
export { default as Td } from './Td.svelte';
export { default as List } from './List.svelte';
export { default as ListItem } from './ListItem.svelte';
export { default as Legend, type LegendItem } from './Legend.svelte';
export { default as Strata, type Stratum } from './Strata.svelte';
export { default as MiniBars } from './MiniBars.svelte';

// hlášení
export { default as IssueList, type IssueItem } from './IssueList.svelte';
export { default as CheckBadge } from './CheckBadge.svelte';
export { default as Banner } from './Banner.svelte';
export { default as Toast } from './Toast.svelte';
export { default as Popover } from './Popover.svelte';
export { default as Disclosure } from './Disclosure.svelte';
export { default as ConfirmDialog } from './ConfirmDialog.svelte';

// čas, mapy a grafy
export { default as TimeAxis, type AxisMarker } from './TimeAxis.svelte';
export { default as EventLanes, type Lane, type LaneEvent } from './EventLanes.svelte';
export {
	default as WorldMap,
	type MapColor,
	type EdgeStyle,
	type Hatch,
	type MapLabel,
	type MapMarker,
	type MapArrow,
	type MapEdit
} from './WorldMap.svelte';
export type { MapRegion, MapVillage } from './map/geometry';
export { default as LanguageRiver, type RiverStream } from './LanguageRiver.svelte';

// barvy
export { languagePalette, familyColor, shadeOf, cssVar, type ColorLineage, type LanguagePalette } from './color';
export { formatYear } from './format';
