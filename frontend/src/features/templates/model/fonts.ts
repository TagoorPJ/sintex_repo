import { create } from 'zustand';
import type { FontWeight } from './types';
import { getStudioBase } from '../../../app/env';

// Mirrors renderer/greeting_renderer/fonts.py and uses the same TTFs (public/fonts)
// so our measurements match the server render.
export interface FontFamily {
  id: string;
  label: string;
  category: string;
  hint?: string;
  weights: FontWeight[];
  selectable: boolean;
}

export const FONT_FAMILIES: FontFamily[] = [
  { id: 'poppins', label: 'Poppins', category: 'Sans serif', weights: [400, 500, 600, 700], selectable: true },
  { id: 'inter', label: 'Inter', category: 'Sans serif', weights: [400, 500, 600, 700], selectable: true },
  { id: 'mukta', label: 'Mukta', category: 'Sans serif · Hindi', hint: 'Latin + Devanagari', weights: [400, 500, 600, 700], selectable: true },
  { id: 'playfair', label: 'Playfair Display', category: 'Serif', weights: [400, 600, 700], selectable: true },
  { id: 'cinzel', label: 'Cinzel', category: 'Display serif', weights: [400, 600, 700], selectable: true },
  { id: 'greatvibes', label: 'Great Vibes', category: 'Script', hint: 'Best for names', weights: [400], selectable: true },
  { id: 'muktavaani', label: 'Mukta Vaani', category: 'Gujarati fallback', weights: [400, 500, 600, 700], selectable: false },
];

export const DEFAULT_FAMILY = 'poppins';

const BY_ID = new Map(FONT_FAMILIES.map((f) => [f.id, f]));
const FONT_BASE = `${getStudioBase()}/fonts`;

export function getFamily(id: string): FontFamily {
  return BY_ID.get(id) ?? BY_ID.get(DEFAULT_FAMILY)!;
}

export const cssFamily = (id: string) => `"tpl-${id}"`;

const DEVANAGARI = /[\u0900-\u097F]/;
const GUJARATI = /[\u0A80-\u0AFF]/;
const INDIC = /[\u0900-\u097F\u0A80-\u0AFF]/;

export const isIndic = (text: string) => INDIC.test(text);

// same as resolve_family() in python: Devanagari/Gujarati text falls back to a font that covers it
export function resolveFamily(familyId: string, text: string): FontFamily {
  if (GUJARATI.test(text)) return BY_ID.get('muktavaani')!;
  if (DEVANAGARI.test(text)) return BY_ID.get('mukta')!;
  return getFamily(familyId);
}

export function nearestWeight(family: FontFamily, weight: number): FontWeight {
  return [...family.weights].sort((a, b) => Math.abs(a - weight) - Math.abs(b - weight) || b - a)[0];
}

// loading

// bumped on every font load so layouts get recomputed
export const useFontsVersion = create<{ version: number }>(() => ({ version: 0 }));

const loading = new Map<string, Promise<void>>();
// track this ourselves, document.fonts.check() returns true for families that were never declared
const loaded = new Set<string>();

export function ensureFont(familyId: string, weight: number): Promise<void> {
  const family = getFamily(familyId);
  const w = nearestWeight(family, weight);
  const key = `${family.id}-${w}`;
  let promise = loading.get(key);
  if (!promise) {
    const face = new FontFace(`tpl-${family.id}`, `url(${FONT_BASE}/${key}.ttf)`, { weight: String(w) });
    promise = face
      .load()
      .then((ready) => {
        document.fonts.add(ready);
        loaded.add(key);
        measureCache.clear();
        useFontsVersion.setState((s) => ({ version: s.version + 1 }));
      })
      .catch(() => {
        loading.delete(key); // so it can retry later
      });
    loading.set(key, promise);
  }
  return promise;
}

export function isFontLoaded(familyId: string, weight: number): boolean {
  const family = getFamily(familyId);
  return loaded.has(`${family.id}-${nearestWeight(family, weight)}`);
}

export function preloadDefaultFonts(): Promise<unknown> {
  return Promise.all([400, 500, 600, 700].map((w) => ensureFont(DEFAULT_FAMILY, w)));
}

// measuring

let ctx: CanvasRenderingContext2D | null = null;
const measureCache = new Map<string, number>();

/** advance width in px, without letter spacing */
export function measureText(text: string, familyId: string, weight: number, size: number): number {
  const key = `${familyId}|${weight}|${size}|${text}`;
  const hit = measureCache.get(key);
  if (hit !== undefined) return hit;
  if (!isFontLoaded(familyId, weight)) void ensureFont(familyId, weight);
  ctx ??= document.createElement('canvas').getContext('2d')!;
  ctx.font = `${weight} ${size}px ${cssFamily(familyId)}, sans-serif`;
  const width = ctx.measureText(text).width;
  if (measureCache.size > 20000) measureCache.clear();
  measureCache.set(key, width);
  return width;
}
