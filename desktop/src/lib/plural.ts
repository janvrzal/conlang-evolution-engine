/** Česká množná čísla: 1 ves, 2–4 vsi, 5 vsí. */
export function plural(n: number, one: string, few: string, many: string): string {
	if (n === 1) return one;
	return n >= 2 && n <= 4 ? few : many;
}
