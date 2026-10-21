import { describe, expect, it, vi } from 'vitest';

// mirrors renderer/tests/test_layout.py, both sides have to give the same answers
vi.mock('./fonts', () => ({
  isIndic: (t: string) => /[ऀ-ॿ઀-૿]/.test(t),
  resolveFamily: () => ({ id: 'poppins', weights: [700] }),
  nearestWeight: () => 700,
  measureText: () => 0,
}));

const { applyCase, cleanText, layoutText, resolveText } = await import('./layout');
import type { TextField } from './types';

const measure = (text: string, _f: string, _w: number, size: number) => Array.from(text).length * size * 0.5;

function make(width = 300, size = 40, minSize = 30, maxLines: 1 | 2 = 1, extra: Partial<TextField> = {}): TextField {
  return {
    id: 'f1',
    kind: 'variable',
    variable: 'name',
    text: null,
    label: null,
    box: { x: 0, y: 0, width },
    style: { fontFamily: 'poppins', fontWeight: 700, fontSize: size, color: '#1F1F1F', align: 'center', letterSpacing: 0, lineHeight: 1.25, textCase: 'none', shadow: false },
    fit: { minFontSize: minSize, maxLines },
    whenEmpty: { mode: 'hide', text: '' },
    ...extra,
  };
}

describe('layoutText (parity with greeting_renderer.layout)', () => {
  it('fits at base size', () => {
    const lay = layoutText('Rahul', make(), measure);
    expect([lay.fontSize, lay.lines, lay.overflow]).toEqual([40, ['Rahul'], 'none']);
  });
  it('shrinks before anything else', () => {
    const lay = layoutText('Rahul Prakash Shar', make(), measure);
    expect([lay.fontSize, lay.overflow]).toEqual([33, 'shrunk']);
  });
  it('wraps at the largest size when two lines are allowed', () => {
    const lay = layoutText('Welspun India Limited Company', make(300, 40, 30, 2), measure);
    expect(lay.overflow).toBe('wrapped');
    expect(lay.lines).toHaveLength(2);
    lay.lines.forEach((l) => expect(measure(l, '', 0, lay.fontSize)).toBeLessThanOrEqual(300));
  });
  it('truncates with an ellipsis at the minimum size', () => {
    const lay = layoutText('A'.repeat(40), make(), measure);
    expect(lay.overflow).toBe('truncated');
    expect(lay.fontSize).toBe(30);
    expect(lay.lines[0].endsWith('…')).toBe(true);
    expect(measure(lay.lines[0], '', 0, 30)).toBeLessThanOrEqual(300);
  });
  it('centres the block vertically', () => {
    const lay = layoutText('Rahul', make(300, 40, 30, 2), measure);
    expect([lay.boxHeight, lay.blockTop]).toEqual([100, 25]);
  });
  it('normalises values', () => {
    expect(cleanText('  vishal \n  verma 🎉 ')).toBe('vishal verma');
    expect(applyCase('vishal VERMA', 'title')).toBe('Vishal Verma');
  });
  it('hides empty values or shows the fallback', () => {
    expect(resolveText(make(), { name: '  ' })).toBeNull();
    expect(resolveText(make(300, 40, 30, 1, { whenEmpty: { mode: 'fallback', text: 'Valued Partner' } }), {})).toBe('Valued Partner');
  });
});
