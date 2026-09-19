import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

/**
 * Typové pomůcky, které očekávají komponenty ze shadcn-svelte.
 *
 * Generátor je do `utils.ts` nedoplnil, takže na `import type { WithElementRef }`
 * padalo 24 z 32 chyb type-checku — v každé komponentě jedna.
 */

/** Props komponenty rozšířené o `ref` na podkladový DOM element. */
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & {
	ref?: U | null;
};

/** Props bez `children` — pro komponenty, které si obsah skládají samy. */
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T;

/** Props bez `child` — pro komponenty bez render delegace. */
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T;

/** Props bez `children` i `child` zároveň. */
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
