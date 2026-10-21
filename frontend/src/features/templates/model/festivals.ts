import type { Festival } from './types';

// keep in sync with SEED in renderer/greeting_renderer/festivals.py
export const SEED_FESTIVALS: Array<[id: string, label: string, aliases: string[]]> = [
  ['diwali', 'Diwali', ['Deepavali', 'Deepawali', 'Divali']],
  ['holi', 'Holi', ['Rangwali Holi', 'Dhulandi']],
  ['navratri', 'Navratri', ['Navaratri', 'Garba']],
  ['dussehra', 'Dussehra', ['Dasara', 'Vijayadashami']],
  ['ganesh-chaturthi', 'Ganesh Chaturthi', ['Ganeshotsav', 'Vinayaka Chaturthi']],
  ['raksha-bandhan', 'Raksha Bandhan', ['Rakhi']],
  ['janmashtami', 'Janmashtami', ['Krishna Janmashtami', 'Gokulashtami']],
  ['makar-sankranti', 'Makar Sankranti', ['Sankranti', 'Uttarayan', 'Pongal', 'Lohri']],
  ['gudi-padwa', 'Gudi Padwa', ['Ugadi']],
  ['baisakhi', 'Baisakhi', ['Vaisakhi']],
  ['onam', 'Onam', []],
  ['eid-al-fitr', 'Eid al-Fitr', ['Eid', 'Ramzan Eid', 'Eid ul Fitr', 'Ramadan Eid']],
  ['eid-al-adha', 'Eid al-Adha', ['Bakrid', 'Bakri Eid', 'Eid ul Adha']],
  ['christmas', 'Christmas', ['Xmas', 'Merry Christmas']],
  ['new-year', 'New Year', ['Happy New Year']],
  ['independence-day', 'Independence Day', ['15 August']],
  ['republic-day', 'Republic Day', ['26 January']],
];

export function seedFestivals(): Festival[] {
  return SEED_FESTIVALS.map(([id, label, aliases]) => ({ id, label, aliases, nextDate: null, activeTemplateId: null }));
}

export function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

// exact match on id/label/alias, used to block duplicates
export function findFestival(text: string, festivals: Festival[]): Festival | undefined {
  const wanted = norm(text);
  return festivals.find((f) => [f.id, f.label, ...f.aliases].some((n) => norm(n) === wanted));
}
