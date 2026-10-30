import type { PointerEvent as ReactPointerEvent } from 'react';
import { clampBox, fieldRect, snapMove } from '../../model/geometry';
import { boxHeight } from '../../model/layout';
import type { Box, TextField } from '../../model/types';
import { fieldLabel, MAX_FONT, MIN_FONT } from '../../model/variables';
import { announce } from '../actions';
import { clearGesture, docActions, effectiveZoom, useDoc, useEditor, useGesture } from '../state';

export type Handle = 'w' | 'e' | 'nw' | 'ne' | 'sw' | 'se';

const DRAG_THRESHOLD = 3; // screen px before a press counts as a drag
const SNAP_PX = 6; // screen px

// only the gesture store updates while dragging (once per rAF). the doc gets
// written once on pointerup so each drag/resize is a single undo step
function track(
  e: ReactPointerEvent,
  onMove: (dx: number, dy: number, ev: PointerEvent) => void,
  onEnd: (moved: boolean) => void,
) {
  const target = e.currentTarget as HTMLElement;
  const pointerId = e.pointerId;
  target.setPointerCapture?.(pointerId);
  const startX = e.clientX;
  const startY = e.clientY;
  let moved = false;
  let frame = 0;
  let last: PointerEvent | null = null;

  const flush = () => {
    frame = 0;
    if (!last) return;
    const zoom = effectiveZoom(useEditor.getState());
    onMove((last.clientX - startX) / zoom, (last.clientY - startY) / zoom, last);
  };
  const move = (ev: PointerEvent) => {
    if (ev.pointerId !== pointerId) return;
    if (!moved && Math.hypot(ev.clientX - startX, ev.clientY - startY) < DRAG_THRESHOLD) return;
    moved = true;
    last = ev;
    if (!frame) frame = requestAnimationFrame(flush);
  };
  const cleanup = () => {
    cancelAnimationFrame(frame);
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', cancel);
    window.removeEventListener('keydown', key, true);
    target.releasePointerCapture?.(pointerId);
  };
  const up = (ev: PointerEvent) => {
    if (ev.pointerId !== pointerId) return;
    if (frame) flush();
    cleanup();
    onEnd(moved);
  };
  const cancel = () => {
    cleanup();
    clearGesture();
  };
  const key = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopImmediatePropagation();
      cancel(); // snaps back to the start position
    }
  };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', cancel);
  window.addEventListener('keydown', key, true);
}

export function startMove(e: ReactPointerEvent, field: TextField) {
  if (e.button !== 0) return;
  e.stopPropagation();
  useEditor.getState().select(field.id);
  const start = { ...field.box };
  const h = fieldRect(field).h;

  track(
    e,
    (dx, dy, ev) => {
      const { doc } = useDoc.getState();
      const ed = useEditor.getState();
      let x = start.x + dx;
      let y = start.y + dy;
      let guides = useGesture.getState().guides;
      let gaps = useGesture.getState().gaps;
      if (ed.snapping && !ev.altKey) {
        const others = doc.fields.filter((f) => f.id !== field.id).map((f) => fieldRect(f));
        const snapped = snapMove({ x, y, w: start.width, h }, others, doc.canvas, SNAP_PX / effectiveZoom(ed));
        x = snapped.x;
        y = snapped.y;
        guides = snapped.guides;
        gaps = snapped.gaps;
      } else {
        guides = [];
        gaps = [];
      }
      const box = clampBox({ x, y, width: start.width }, h, doc.canvas);
      useGesture.setState({ fieldId: field.id, kind: 'move', box, fontSize: field.style.fontSize, guides, gaps });
    },
    (moved) => {
      const g = useGesture.getState();
      if (moved && g.box && g.fieldId === field.id) {
        const box = { x: Math.round(g.box.x), y: Math.round(g.box.y), width: Math.round(g.box.width) };
        docActions.updateField(field.id, { box });
        announce(`${fieldLabel(field)} moved to X ${box.x}, Y ${box.y}`);
      }
      clearGesture();
    },
  );
}

export function startResize(e: ReactPointerEvent, field: TextField, handle: Handle) {
  if (e.button !== 0) return;
  e.stopPropagation();
  e.preventDefault();
  const start = { ...field.box };
  const startSize = field.style.fontSize;
  const startH = boxHeight(field.style, field.fit.maxLines);
  const { canvas } = useDoc.getState().doc;

  track(
    e,
    (dx, _dy, ev) => {
      let box: Box = { ...start };
      let fontSize = startSize;
      const minW = Math.max(48, startSize * 2);
      if (handle === 'e' || handle === 'w') {
        const symmetric = ev.altKey && field.style.align === 'center';
        const delta = handle === 'e' ? dx : -dx;
        let width = start.width + (symmetric ? delta * 2 : delta);
        const maxW = symmetric ? Math.min(canvas.width, 2 * Math.min(start.x + start.width / 2, canvas.width - start.x - start.width / 2)) : handle === 'e' ? canvas.width - start.x : start.x + start.width;
        width = Math.min(Math.max(width, minW), maxW);
        const x = symmetric ? start.x + (start.width - width) / 2 : handle === 'e' ? start.x : start.x + start.width - width;
        box = { ...start, x, width };
      } else {
        // corners scale font size and width together
        const right = handle === 'ne' || handle === 'se';
        let s = (start.width + (right ? dx : -dx)) / start.width;
        s = Math.min(Math.max(s, MIN_FONT / startSize, minW / 2 / start.width), MAX_FONT / startSize);
        const maxW = right ? canvas.width - start.x : start.x + start.width;
        s = Math.min(s, maxW / start.width);
        fontSize = Math.round(startSize * s);
        const width = start.width * s;
        const h = boxHeight({ ...field.style, fontSize }, field.fit.maxLines);
        const x = right ? start.x : start.x + start.width - width;
        const top = handle === 'nw' || handle === 'ne';
        const y = top ? start.y + startH - h : start.y;
        box = clampBox({ x, y, width }, h, canvas);
      }
      useGesture.setState({ fieldId: field.id, kind: 'resize', box, fontSize, guides: [], gaps: [] });
    },
    (moved) => {
      const g = useGesture.getState();
      if (moved && g.box && g.fieldId === field.id && g.fontSize) {
        const ratio = g.fontSize / startSize;
        docActions.updateField(field.id, {
          box: { x: Math.round(g.box.x), y: Math.round(g.box.y), width: Math.round(g.box.width) },
          style: { fontSize: g.fontSize },
          fit: { minFontSize: Math.max(8, Math.min(g.fontSize, Math.round(field.fit.minFontSize * ratio))) },
        });
        announce(`${fieldLabel(field)} is ${Math.round(g.box.width)} wide, ${g.fontSize} px text`);
      }
      clearGesture();
    },
  );
}
