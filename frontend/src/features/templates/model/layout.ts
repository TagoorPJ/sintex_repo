// Line for line port of renderer/greeting_renderer/layout.py. Change one, change the other.
import { isIndic, measureText, nearestWeight, resolveFamily } from './fonts';
import type { TextField, TextStyle, Values, VariableKey } from './types';

export const MAX_LENGTH: Record<VariableKey, number> = { name: 40, number: 20, enterprise: 60 };
const ELLIPSIS = '\u2026';

// yes these match control chars and emoji/variation selectors on purpose, chatbot input gets cleaned
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001F\u007F-\u009F]/g;
// eslint-disable-next-line no-misleading-character-class
const EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200B}\u{2060}]/gu;
const SPACES = /\s+/g;

export type Overflow = 'none' | 'shrunk' | 'wrapped' | 'truncated';
export type Measure = (text: string, familyId: string, weight: number, size: number) => number;

export function cleanText(raw: string | null | undefined): string {
  if (!raw) return '';
  return raw.replace(CONTROL, ' ').replace(EMOJI, '').replace(SPACES, ' ').trim();
}

export function applyCase(text: string, textCase: TextStyle['textCase']): string {
  if (textCase === 'upper') return text.toUpperCase();
  if (textCase === 'title')
    return text
      .split(' ')
      .map((w) => w.slice(0, 1).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  return text;
}

function truncateChars(text: string, limit: number): string {
  const chars = Array.from(text);
  return chars.length <= limit ? text : chars.slice(0, limit).join('').trimEnd();
}

/** null means the field is hidden */
export function resolveText(f: TextField, values: Values): string | null {
  let text: string;
  if (f.kind === 'text') {
    text = cleanText(f.text);
  } else {
    const key = f.variable ?? 'name';
    text = cleanText(values[key]);
    if (text) text = truncateChars(text, MAX_LENGTH[key]);
  }
  if (!text) {
    if (f.kind === 'variable' && f.whenEmpty.mode === 'fallback') text = cleanText(f.whenEmpty.text);
    if (!text) return null;
  }
  return applyCase(text, f.style.textCase);
}

export interface TextLayout {
  fontSize: number;
  lines: string[];
  lineWidths: number[];
  overflow: Overflow;
  familyId: string;
  weight: number;
  letterSpacing: number; // em, after adjustments
  boxHeight: number;
  blockTop: number;
  lineHeightPx: number;
}

export const boxHeight = (style: TextStyle, maxLines: number) => style.fontSize * style.lineHeight * maxLines;

const pyRound = (n: number) => {
  // python round() does banker's rounding, copy it so sizes match
  const r = Math.round(n);
  return Math.abs(n % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
};

export function layoutText(text: string, f: TextField, measure: Measure = measureText): TextLayout {
  const { style, fit } = f;
  const family = resolveFamily(style.fontFamily, text);
  const weight = nearestWeight(family, style.fontWeight);
  const ls = isIndic(text) ? 0 : style.letterSpacing;
  const width = f.box.width;
  const base = Math.max(1, pyRound(style.fontSize));
  const minimum = Math.max(1, Math.min(base, pyRound(fit.minFontSize)));
  const len = (s: string) => Array.from(s).length;
  const w = (s: string, size: number) => measure(s, family.id, weight, size) + ls * size * len(s);

  const done = (size: number, lines: string[], overflow: Overflow): TextLayout => {
    const lh = size * style.lineHeight;
    const bh = boxHeight(style, fit.maxLines);
    return {
      fontSize: size,
      lines,
      lineWidths: lines.map((line) => w(line, size)),
      overflow,
      familyId: family.id,
      weight,
      letterSpacing: ls,
      boxHeight: bh,
      blockTop: (bh - lh * lines.length) / 2,
      lineHeightPx: lh,
    };
  };

  for (let size = base; size >= minimum; size--) {
    if (w(text, size) <= width) return done(size, [text], size === base ? 'none' : 'shrunk');
  }
  if (fit.maxLines === 2) {
    for (let size = base; size >= minimum; size--) {
      const lines = wrap(text, size, width, w);
      if (lines.length <= 2 && lines.every((line) => w(line, size) <= width)) return done(size, lines, 'wrapped');
    }
  }
  const lines = fit.maxLines === 2 ? wrap(text, minimum, width, w) : [text];
  const kept = lines.slice(0, fit.maxLines);
  if (lines.length > fit.maxLines) kept[kept.length - 1] = lines.slice(fit.maxLines - 1).join(' ');
  return done(
    minimum,
    kept.map((line) => ellipsize(line, minimum, width, w)),
    'truncated',
  );
}

function wrap(text: string, size: number, width: number, w: (s: string, size: number) => number): string[] {
  const lines: string[] = [];
  let current = '';
  for (const word of text.split(' ')) {
    const candidate = current ? `${current} ${word}` : word;
    if (current && w(candidate, size) > width) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function ellipsize(line: string, size: number, width: number, w: (s: string, size: number) => number): string {
  if (w(line, size) <= width) return line;
  let chars = Array.from(line);
  while (chars.length && w(chars.join('').trimEnd() + ELLIPSIS, size) > width) chars = chars.slice(0, -1);
  return chars.join('').trimEnd() + ELLIPSIS;
}
