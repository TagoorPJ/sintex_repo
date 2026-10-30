import { boxHeight } from './layout';
import type { Box, Canvas, TextField } from './types';
import { safeMargin } from './variables';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Guide {
  axis: 'x' | 'y'; // x means a vertical line at pos
  pos: number;
}

export interface GapGuide {
  x: number;
  y1: number;
  y2: number;
}

export function fieldRect(f: TextField, box: Box = f.box, fontSize = f.style.fontSize): Rect {
  return { x: box.x, y: box.y, w: box.width, h: boxHeight({ ...f.style, fontSize }, f.fit.maxLines) };
}

export function clampBox(box: Box, height: number, canvas: Canvas): Box {
  const width = Math.min(box.width, canvas.width);
  return {
    width,
    x: Math.min(Math.max(0, box.x), canvas.width - width),
    y: Math.min(Math.max(0, box.y), Math.max(0, canvas.height - height)),
  };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

interface Candidate {
  diff: number;
  guide?: Guide;
  gaps?: GapGuide[];
}

function best(candidates: Candidate[], threshold: number): Candidate | null {
  let winner: Candidate | null = null;
  for (const c of candidates) {
    if (Math.abs(c.diff) <= threshold && (!winner || Math.abs(c.diff) < Math.abs(winner.diff))) winner = c;
  }
  return winner;
}

// Snaps to canvas centre/edges/safe margin, other fields' edges and centres,
// and equal vertical gaps. threshold is in image px.
export function snapMove(rect: Rect, others: Rect[], canvas: Canvas, threshold: number) {
  const m = safeMargin(canvas);
  const xTargets = [0, m, canvas.width / 2, canvas.width - m, canvas.width, ...others.flatMap((o) => [o.x, o.x + o.w / 2, o.x + o.w])];
  const yTargets = [0, m, canvas.height / 2, canvas.height - m, canvas.height, ...others.flatMap((o) => [o.y, o.y + o.h / 2, o.y + o.h])];
  const xAnchors = [0, rect.w / 2, rect.w];
  const yAnchors = [0, rect.h / 2, rect.h];

  const xCands: Candidate[] = xTargets.flatMap((t) => xAnchors.map((a) => ({ diff: t - (rect.x + a), guide: { axis: 'x' as const, pos: t } })));
  const yCands: Candidate[] = yTargets.flatMap((t) => yAnchors.map((a) => ({ diff: t - (rect.y + a), guide: { axis: 'y' as const, pos: t } })));

  // equal spacing - match any gap already between two other fields
  const sorted = [...others].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) {
    const a = sorted[i - 1];
    const b = sorted[i];
    const gap = b.y - (a.y + a.h);
    if (gap < 0) continue;
    const pairGuide: GapGuide = { x: Math.max(a.x, b.x) + Math.min(a.w, b.w) / 2, y1: a.y + a.h, y2: b.y };
    for (const o of others) {
      const below = o.y + o.h + gap;
      yCands.push({ diff: below - rect.y, gaps: [pairGuide, { x: rect.x + rect.w / 2, y1: o.y + o.h, y2: below }] });
      const above = o.y - gap - rect.h;
      yCands.push({ diff: above - rect.y, gaps: [pairGuide, { x: rect.x + rect.w / 2, y1: above + rect.h, y2: o.y }] });
    }
  }

  const bx = best(xCands, threshold);
  const by = best(yCands, threshold);
  const guides: Guide[] = [];
  if (bx?.guide) guides.push(bx.guide);
  if (by?.guide) guides.push(by.guide);
  return {
    x: rect.x + (bx?.diff ?? 0),
    y: rect.y + (by?.diff ?? 0),
    guides,
    gaps: by?.gaps ?? [],
  };
}
