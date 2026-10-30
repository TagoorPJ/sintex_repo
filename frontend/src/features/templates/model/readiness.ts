import type { TextField } from './types';

interface Subject {
  festivalId: string | null;
  background: unknown | null;
  fields: TextField[];
}

// what's left before the chatbot can use it. empty list means live
export function missingForLive(t: Subject): string[] {
  const missing: string[] = [];
  if (!t.background) missing.push('a background image');
  if (!t.festivalId) missing.push('a festival');
  if (!t.fields.some((f) => f.kind === 'variable')) missing.push('at least one field (Name, Number or Enterprise Name)');
  return missing;
}

export const isLive = (t: Subject) => missingForLive(t).length === 0;
