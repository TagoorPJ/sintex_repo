import { toast } from 'sonner';
import { clampBox, fieldRect } from '../model/geometry';
import { boxHeight } from '../model/layout';
import type { Asset, Canvas, TextField, TextStyle, Values, VariableKey } from '../model/types';
import { createField, defaultStyle, fieldLabel, MAX_TEXT_ELEMENTS, SCENARIOS, STACK_ORDER } from '../model/variables';
import { docActions, useDoc, useEditor, type Doc } from './state';

export function currentValues(): Values {
  const { scenario, custom } = useEditor.getState();
  return scenario === 'custom' ? custom : SCENARIOS[scenario].values;
}

// dark brand tone on light art, white + shadow on dark
function autoColour(canvas: Canvas, box: { x: number; y: number; width: number }, height: number): Pick<TextStyle, 'color' | 'shadow'> {
  const analysis = useEditor.getState().analysis;
  if (!analysis) return { color: '#1F1F1F', shadow: false };
  const lum = analysis.sample(box.x, box.y, box.width, Math.min(height, canvas.height - box.y));
  return lum > 0.55 ? { color: analysis.darkAccent ?? '#1F1F1F', shadow: false } : { color: '#FFFFFF', shadow: true };
}

function stackFields(fields: TextField[]) {
  return [...fields].sort((a, b) => a.box.y - b.box.y);
}

function placeNew(doc: Doc, field: TextField, at?: { x: number; y: number }, above = false): TextField {
  const { canvas } = doc;
  const h = boxHeight(field.style, field.fit.maxLines);
  let { x, y } = field.box;
  if (at) {
    x = at.x - field.box.width / 2;
    y = at.y - h / 2;
  } else if (doc.fields.length) {
    const sorted = stackFields(doc.fields);
    const gap = Math.round(field.style.fontSize * 0.4);
    if (above) {
      y = sorted[0].box.y - h - gap;
    } else {
      const last = sorted[sorted.length - 1];
      y = last.box.y + fieldRect(last).h + gap;
    }
    const ref = sorted[sorted.length - 1];
    x = ref.box.x;
  }
  return { ...field, box: clampBox({ x, y, width: field.box.width }, h, canvas) };
}

export function addVariable(key: VariableKey, at?: { x: number; y: number }) {
  const { doc } = useDoc.getState();
  const existing = doc.fields.find((f) => f.kind === 'variable' && f.variable === key);
  if (existing) {
    useEditor.getState().select(existing.id);
    return;
  }
  // copy style from an existing variable so the stack looks consistent
  const sibling = doc.fields.find((f) => f.kind === 'variable');
  let field = createField(doc.canvas, 'variable', key, sibling ? { style: { ...sibling.style }, box: { ...sibling.box }, fit: { ...sibling.fit } } : {});
  // stacks below in Name, Enterprise, Number order
  field = placeNew(doc, field, at);
  if (!sibling) field = { ...field, style: { ...field.style, ...autoColour(doc.canvas, field.box, fieldRect(field).h) } };
  docActions.addField(field);
  useEditor.getState().select(field.id);
  announce(`${fieldLabel(field)} added`);
}

export function addText(at?: { x: number; y: number }) {
  const { doc } = useDoc.getState();
  if (doc.fields.filter((f) => f.kind === 'text').length >= MAX_TEXT_ELEMENTS) {
    toast.error(`A template can have up to ${MAX_TEXT_ELEMENTS} text elements.`);
    return;
  }
  const base = createField(doc.canvas, 'text', null, {
    style: defaultStyle(doc.canvas, { fontWeight: 500, fontSize: Math.round(doc.canvas.width * 0.037) }),
  });
  let field = placeNew(doc, base, at, true);
  field = { ...field, style: { ...field.style, ...autoColour(doc.canvas, field.box, fieldRect(field).h) } };
  docActions.addField(field);
  useEditor.getState().select(field.id);
  announce('Text added');
}

// top and bottom stay put, the rest get even gaps, everything centred horizontally
export function stackEvenly() {
  const { doc } = useDoc.getState();
  const sorted = stackFields(doc.fields);
  if (sorted.length < 2) return;
  const rects = sorted.map((f) => fieldRect(f));
  const top = rects[0].y;
  const bottom = rects[rects.length - 1].y + rects[rects.length - 1].h;
  const gap = Math.max(0, (bottom - top - rects.reduce((s, r) => s + r.h, 0)) / (sorted.length - 1));
  let y = top;
  const placed = new Map<string, TextField>();
  sorted.forEach((f, i) => {
    placed.set(f.id, { ...f, box: { ...f.box, x: Math.round((doc.canvas.width - f.box.width) / 2), y: Math.round(y) } });
    y += rects[i].h + gap;
  });
  docActions.setFields(doc.fields.map((f) => placed.get(f.id) ?? f));
  announce('Fields stacked evenly');
}

export function applyStyleToAll(sourceId: string) {
  const { doc } = useDoc.getState();
  const src = doc.fields.find((f) => f.id === sourceId);
  if (!src) return;
  const { fontFamily, fontWeight, fontSize, color, shadow, align } = src.style;
  docActions.setFields(
    doc.fields.map((f) =>
      f.id === src.id || f.kind !== 'variable'
        ? f
        : { ...f, style: { ...f.style, fontFamily, fontWeight, fontSize, color, shadow, align }, fit: { ...f.fit, minFontSize: Math.round(fontSize * (src.fit.minFontSize / src.style.fontSize)) } },
    ),
  );
  announce(`${fieldLabel(src)} style applied to all fields`);
}

// same order in the palette and the preview form
export const orderedVariables = STACK_ORDER;

export function setBackground(asset: Asset) {
  const { doc } = useDoc.getState();
  const old = doc.canvas;
  const next: Canvas = { width: asset.width, height: asset.height };
  const sx = next.width / old.width;
  const sy = next.height / old.height;
  const ratioChanged = Math.abs(old.width / old.height - next.width / next.height) > 0.01;
  const fields =
    doc.fields.length && (sx !== 1 || sy !== 1)
      ? doc.fields.map((f) => {
          const fontSize = Math.max(8, Math.round(f.style.fontSize * sx));
          const box = { x: f.box.x * sx, y: f.box.y * sy, width: Math.max(24, f.box.width * sx) };
          const h = boxHeight({ ...f.style, fontSize }, f.fit.maxLines);
          return {
            ...f,
            style: { ...f.style, fontSize },
            fit: { ...f.fit, minFontSize: Math.min(fontSize, Math.max(8, Math.round(f.fit.minFontSize * sx))) },
            box: clampBox({ x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width) }, h, next),
          };
        })
      : doc.fields;
  useDoc.getState().commit((d) => ({ ...d, background: asset, canvas: next, fields }));
  if (doc.background && doc.fields.length && ratioChanged) {
    toast.warning('Image proportions changed. Check field positions.', {
      action: { label: 'Preview', onClick: () => useEditor.getState().set({ mode: 'preview' }) },
    });
  }
}

export function removeBackground() {
  useDoc.getState().commit((d) => ({ ...d, background: null }));
  useEditor.getState().set({ analysis: null, notices: [] });
}

export function nudge(dx: number, dy: number) {
  const { selectedId } = useEditor.getState();
  const { doc } = useDoc.getState();
  const f = doc.fields.find((x) => x.id === selectedId);
  if (!f) return;
  const box = clampBox({ ...f.box, x: f.box.x + dx, y: f.box.y + dy }, fieldRect(f).h, doc.canvas);
  docActions.updateField(f.id, { box }, `nudge:${f.id}`);
  announce(`${fieldLabel(f)} at X ${Math.round(box.x)}, Y ${Math.round(box.y)}`);
}

export function deleteSelected() {
  const { selectedId } = useEditor.getState();
  const f = useDoc.getState().doc.fields.find((x) => x.id === selectedId);
  if (!f) return;
  docActions.removeField(f.id);
  useEditor.getState().select(null);
  toast(`${fieldLabel(f)} removed`, { action: { label: 'Undo', onClick: () => useDoc.getState().undo() } });
}

let announceTimer: ReturnType<typeof setTimeout> | undefined;
export function announce(message: string) {
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => useEditor.getState().set({ announce: message }), 150);
}
