import { cssFamily, ensureFont, nearestWeight, resolveFamily } from '../model/fonts';
import { layoutText, resolveText } from '../model/layout';
import type { Canvas, TextField, Values } from '../model/types';

// Client-side PNG for Download PNG when there's no backend.
// Same layout rules as the Pillow renderer, keep them in sync
export async function renderToBlob(canvasSize: Canvas, backgroundUrl: string | null, fields: TextField[], values: Values): Promise<Blob> {
  const resolved = fields.map((f) => ({ f, text: resolveText(f, values) }));
  await Promise.all(
    resolved.map(({ f, text }) => {
      const fam = resolveFamily(f.style.fontFamily, text ?? '');
      return ensureFont(fam.id, nearestWeight(fam, f.style.fontWeight));
    }),
  );

  const canvas = document.createElement('canvas');
  canvas.width = canvasSize.width;
  canvas.height = canvasSize.height;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (backgroundUrl) {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.src = backgroundUrl;
    await img.decode();
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  }

  for (const { f, text } of resolved) {
    if (text === null) continue;
    const lay = layoutText(text, f);
    ctx.font = `${lay.weight} ${lay.fontSize}px ${cssFamily(lay.familyId)}, sans-serif`;
    ctx.letterSpacing = lay.letterSpacing ? `${lay.letterSpacing * lay.fontSize}px` : '0px';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = f.style.color;
    const m = ctx.measureText('Hg');
    const ascent = m.fontBoundingBoxAscent;
    const descent = m.fontBoundingBoxDescent;
    if (f.style.shadow) {
      ctx.shadowColor = 'rgba(0,0,0,0.45)';
      ctx.shadowBlur = lay.fontSize * 0.12;
      ctx.shadowOffsetY = lay.fontSize * 0.04;
    } else {
      ctx.shadowColor = 'transparent';
    }
    lay.lines.forEach((line, i) => {
      const lineW = lay.lineWidths[i];
      const x = f.style.align === 'left' ? f.box.x : f.style.align === 'right' ? f.box.x + f.box.width - lineW : f.box.x + (f.box.width - lineW) / 2;
      const lineTop = f.box.y + lay.blockTop + i * lay.lineHeightPx;
      const baseline = lineTop + (lay.lineHeightPx - (ascent + descent)) / 2 + ascent;
      ctx.fillText(line, x, baseline);
    });
  }

  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not encode image'))), 'image/png'));
}

export function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: fileName });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
