// Texty obrazovky „projekty“ (klíče s předponou projekty.). Anglický katalog musí mít stejné klíče (hlídá typ).
import { plural } from '../../plural';
import type { Message } from '../types';

export const cs = {
} satisfies Record<string, Message>;

export const en: Record<keyof typeof cs, Message> = {
};

void plural;
