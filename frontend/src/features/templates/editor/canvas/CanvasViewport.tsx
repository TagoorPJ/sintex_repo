import { Building2, ImageUp, Phone, Type, User } from 'lucide-react';
import { memo, useEffect, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Notice } from '@/components/ui/feedback';
import { cn } from '@/lib/cn';
import { boxHeight } from '../../model/layout';
import type { TextField, VariableKey } from '../../model/types';
import { fieldLabel, SCENARIOS, TOKEN_VALUES } from '../../model/variables';
import { FieldText, useFieldLayout } from '../../render/FieldText';
import { addText, addVariable } from '../actions';
import { useImageUpload } from '../hooks';
import { effectiveZoom, useDoc, useEditor, useGesture } from '../state';
import { startMove, startResize, type Handle } from './gestures';

export const DRAG_MIME = 'application/x-greeting-field';

export const VARIABLE_ICON: Record<VariableKey, typeof User> = { name: User, enterprise: Building2, number: Phone };
export const VARIABLE_TINT: Record<VariableKey, string> = {
  name: 'bg-[#E6F6F8] text-[#0A6F86] dark:bg-[#0E2A30] dark:text-[#6FF7EF]',
  enterprise: 'bg-[#FBF4E2] text-[#8A6410] dark:bg-[#2A2008] dark:text-[#F5D77A]',
  number: 'bg-[#ECEDF8] text-[#3D49A8] dark:bg-[#1B1D3A] dark:text-[#A9B0F0]',
};
export const TEXT_TINT = 'bg-sunken text-fg-2';

export function FieldIcon({ field, className }: { field: TextField; className?: string }) {
  const Icon = field.kind === 'variable' && field.variable ? VARIABLE_ICON[field.variable] : Type;
  return <Icon className={className} aria-hidden />;
}

// tokens while designing (unless sample text is on), scenario values in preview
const useValues = () =>
  useEditor((s) =>
    s.mode === 'edit' && s.canvasText === 'tokens'
      ? TOKEN_VALUES
      : s.scenario === 'custom'
        ? s.custom
        : (SCENARIOS[s.scenario]?.values ?? SCENARIOS.typical.values),
  );

const FieldVisual = memo(function FieldVisual({ field, mode }: { field: TextField; mode: 'edit' | 'preview' }) {
  const g = useGesture((s) => (s.fieldId === field.id ? s : null));
  const values = useValues();
  const box = g?.box ?? field.box;
  const fontSize = g?.fontSize ?? field.style.fontSize;
  const { layout } = useFieldLayout(field, values, box, fontSize);
  if (layout) return <FieldText field={field} layout={layout} box={box} style={{ animation: 'field-in 180ms var(--ease-out)' }} />;
  if (mode === 'preview') return null;
  // empty field: still show where it sits while editing
  return (
    <div
      aria-hidden
      className="flex items-center justify-center italic"
      style={{
        position: 'absolute',
        left: box.x,
        top: box.y,
        width: box.width,
        height: boxHeight({ ...field.style, fontSize }, field.fit.maxLines),
        fontSize: fontSize * 0.5,
        color: field.style.color,
        opacity: 0.45,
      }}
    >
      {fieldLabel(field)} — hidden when empty
    </div>
  );
});

// live box during a gesture, else the stored one
function useLive(field: TextField) {
  const g = useGesture((s) => (s.fieldId === field.id ? s : null));
  const box = g?.box ?? field.box;
  const fontSize = g?.fontSize ?? field.style.fontSize;
  return { box, fontSize, h: boxHeight({ ...field.style, fontSize }, field.fit.maxLines), gesture: g };
}

const HitBox = memo(function HitBox({ field, zoom, selected, outlines }: { field: TextField; zoom: number; selected: boolean; outlines: boolean }) {
  const { box, h, fontSize } = useLive(field);
  const label = fieldLabel(field);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${label} field, X ${Math.round(box.x)}, Y ${Math.round(box.y)}, ${Math.round(fontSize)} pixel text`}
      aria-describedby="canvas-help"
      onPointerDown={(e) => startMove(e, field)}
      onFocus={() => useEditor.getState().select(field.id)}
      className={cn(
        'group/hit absolute cursor-move touch-none rounded-xs outline-none',
        !selected && outlines && 'outline-1 outline-offset-0 outline-dashed outline-white/60 [box-shadow:0_0_0_1px_rgb(0_0_0/0.18)]',
        !selected && 'hover:outline-2 hover:outline-solid hover:outline-accent',
        'focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-solid focus-visible:outline-accent',
      )}
      style={{ left: box.x * zoom, top: box.y * zoom, width: box.width * zoom, height: h * zoom }}
    >
      {!selected && (
        <span className={cn('pointer-events-none absolute -top-6 left-0 hidden items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium shadow-sm group-hover/hit:inline-flex', tint(field))}>
          <FieldIcon field={field} className="size-3" /> {label}
        </span>
      )}
    </div>
  );
});

const tint = (f: TextField) => (f.kind === 'variable' && f.variable ? VARIABLE_TINT[f.variable] : 'bg-surface text-fg-2');

const HANDLES: Array<{ h: Handle; cls: string; cursor: string }> = [
  { h: 'nw', cls: '-left-1 -top-1', cursor: 'nwse-resize' },
  { h: 'ne', cls: '-right-1 -top-1', cursor: 'nesw-resize' },
  { h: 'sw', cls: '-left-1 -bottom-1', cursor: 'nesw-resize' },
  { h: 'se', cls: '-right-1 -bottom-1', cursor: 'nwse-resize' },
  { h: 'w', cls: '-left-0.75 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
  { h: 'e', cls: '-right-0.75 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
];

function SelectionFrame({ field, zoom }: { field: TextField; zoom: number }) {
  const { box, h, fontSize, gesture } = useLive(field);
  return (
    <div
      className="pointer-events-none absolute transition-opacity duration-100"
      style={{ left: box.x * zoom, top: box.y * zoom, width: box.width * zoom, height: h * zoom }}
    >
      {/* two-tone stroke so it shows on light and dark art */}
      <div className="absolute inset-0 rounded-xs border-[1.5px] border-accent shadow-[0_0_0_1px_rgb(255_255_255/0.9),0_0_0_2px_rgb(0_0_0/0.15)]" />
      <span className={cn('absolute -top-7 left-0 inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-semibold shadow-sm', tint(field))}>
        <FieldIcon field={field} className="size-3" /> {fieldLabel(field)}
      </span>
      {HANDLES.map(({ h: handle, cls, cursor }) => (
        <span
          key={handle}
          aria-hidden
          onPointerDown={(e) => startResize(e, field, handle)}
          className={cn(
            'pointer-events-auto absolute touch-none border-[1.5px] border-accent bg-white shadow-sm',
            handle === 'w' || handle === 'e' ? 'h-4 w-1.5 rounded-full pointer-coarse:h-6 pointer-coarse:w-2.5' : 'size-2 rounded-xs pointer-coarse:size-3.5',
            'after:absolute after:-inset-2 after:content-[""] pointer-coarse:after:-inset-3',
            cls,
          )}
          style={{ cursor }}
        />
      ))}
      {gesture && (
        <span className="tabular absolute left-1/2 top-full mt-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#0f172a] px-1.5 py-0.5 text-[11px] font-medium text-white">
          {gesture.kind === 'move' ? `X ${Math.round(box.x)} · Y ${Math.round(box.y)}` : `W ${Math.round(box.width)} · ${Math.round(fontSize)} px`}
        </span>
      )}
    </div>
  );
}

function Guides({ zoom, width, height }: { zoom: number; width: number; height: number }) {
  const guides = useGesture((s) => s.guides);
  const gaps = useGesture((s) => s.gaps);
  return (
    <>
      {guides.map((g, i) =>
        g.axis === 'x' ? (
          <div key={i} className="pointer-events-none absolute top-0 w-px bg-accent" style={{ left: g.pos * zoom, height: height * zoom }} />
        ) : (
          <div key={i} className="pointer-events-none absolute left-0 h-px bg-accent" style={{ top: g.pos * zoom, width: width * zoom }} />
        ),
      )}
      {gaps.map((g, i) => (
        <div key={`gap${i}`} className="pointer-events-none absolute w-px bg-[#E11D74]" style={{ left: g.x * zoom, top: g.y1 * zoom, height: Math.max(1, (g.y2 - g.y1) * zoom) }}>
          <span className="tabular absolute left-1.5 top-1/2 -translate-y-1/2 rounded bg-[#E11D74] px-1 text-[10px] font-semibold text-white">{Math.round(g.y2 - g.y1)}</span>
        </div>
      ))}
    </>
  );
}

function EmptyDropzone({ onFile, dragOver }: { onFile: (f: File) => void; dragOver: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useEditor((s) => s.upload);
  const notices = useEditor((s) => s.notices);
  const busy = upload.status === 'uploading';
  return (
    <div
      className={cn(
        'fade-in flex w-full max-w-140 flex-col items-center rounded-2xl border-[1.5px] border-dashed px-8 py-12 text-center transition-colors duration-150',
        dragOver ? 'border-accent bg-accent-subtle' : 'border-line-strong bg-surface/60',
      )}
    >
      {busy && upload.localUrl ? (
        <>
          <img src={upload.localUrl} alt="" className="artboard-in mb-5 max-h-56 rounded-lg shadow-artboard" />
          <p className="text-sm font-medium text-fg">Uploading… {Math.round(upload.progress * 100)}%</p>
          <div className="mt-3 h-1 w-56 overflow-hidden rounded-full bg-sunken" role="progressbar" aria-valuenow={Math.round(upload.progress * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
            <div className="h-full bg-accent transition-[width] duration-150" style={{ width: `${upload.progress * 100}%` }} />
          </div>
        </>
      ) : (
        <>
          <div className="mb-5 flex size-14 items-center justify-center rounded-full bg-accent-subtle text-accent-strong">
            <ImageUp className="size-6" aria-hidden />
          </div>
          <h2 className="text-base font-semibold text-fg">{dragOver ? 'Drop to upload' : 'No template image yet'}</h2>
          <p className="mt-1 text-sm text-fg-2">Upload a festive image to start designing your greeting card.</p>
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
          <Button variant="primary" className="mt-5" icon={<ImageUp className="size-4" />} onClick={() => input.current?.click()}>
            Upload image
          </Button>
          <p className="mt-2 text-[12px] text-fg-3">or drag and drop</p>
          <p className="mt-4 text-[12px] text-fg-3">PNG · JPG · WEBP · up to 15 MB · 1080 px+ recommended</p>
          {upload.status === 'error' && (
            <Notice level="error" className="mt-4 w-full text-left">
              Upload failed: {upload.message}
            </Notice>
          )}
          {notices
            .filter((n) => n.level === 'error')
            .map((n) => (
              <Notice key={n.message} level="error" className="mt-4 w-full text-left">
                {n.message}
              </Notice>
            ))}
        </>
      )}
    </div>
  );
}

export function CanvasViewport() {
  const canvas = useDoc((s) => s.doc.canvas);
  const background = useDoc((s) => s.doc.background);
  const fields = useDoc((s) => s.doc.fields);
  const mode = useEditor((s) => s.mode);
  const zoom = useEditor(effectiveZoom);
  const selectedId = useEditor((s) => s.selectedId);
  const outlines = useEditor((s) => s.showOutlines);
  const upload = useEditor((s) => s.upload);
  const serverImage = useEditor((s) => s.serverImage);
  const compare = useEditor((s) => s.compare);
  const announcement = useEditor((s) => s.announce);
  const onFile = useImageUpload();

  const viewport = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [pendingReplace, setPendingReplace] = useState<File | null>(null);
  const [panning, setPanning] = useState(false);

  // recompute fit scale when the viewport resizes
  useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    let rafId: number | null = null;
    const update = () => {
      if (!canvas.width || !canvas.height) return;
      const pad = el.clientWidth < 640 ? 32 : 96;
      // under 1024px the collapsed bottom sheet sits over the canvas, leave room for it
      const sheet = window.innerWidth < 1024 ? 56 : 0;
      const availW = Math.max(0, el.clientWidth - pad);
      const availH = Math.max(0, el.clientHeight - pad - sheet);
      if (availW === 0 || availH === 0) return;
      const s = Math.min(availW / canvas.width, availH / canvas.height);
      const next = Math.max(0.05, Math.min(s, 4));
      const current = useEditor.getState().fitScale;
      // Guard against ResizeObserver ping-pong loops
      if (Math.abs(current - next) > 0.005) {
        useEditor.getState().set({ fitScale: next });
      }
    };
    const onResize = () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(update);
    };
    update();
    const ro = new ResizeObserver(onResize);
    ro.observe(el);
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, [canvas.width, canvas.height]);

  // ctrl/cmd + wheel zooms, trackpad pinch comes through the same way
  useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const ed = useEditor.getState();
      const z = effectiveZoom(ed) * Math.exp(-e.deltaY * 0.002);
      ed.set({ zoom: Math.min(4, Math.max(0.05, z)) });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // hold space and drag to pan
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !(e.target as HTMLElement).closest('input,textarea,[role="button"],button')) {
        e.preventDefault();
        setPanning(true);
      }
    };
    const up = (e: KeyboardEvent) => e.code === 'Space' && setPanning(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  const onPointerDown = (e: ReactPointerEvent) => {
    if (panning && viewport.current) {
      const el = viewport.current;
      const sx = e.clientX + el.scrollLeft;
      const sy = e.clientY + el.scrollTop;
      const move = (ev: PointerEvent) => el.scrollTo(sx - ev.clientX, sy - ev.clientY);
      const upFn = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', upFn);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', upFn);
      return;
    }
    // click on empty canvas deselects
    if (!(e.target as HTMLElement).closest('[role="button"]')) useEditor.getState().select(null);
  };

  const onDragOver = (e: DragEvent) => {
    const types = Array.from(e.dataTransfer.types);
    if (types.includes('Files') || types.includes(DRAG_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      setDragOver(true);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (background) setPendingReplace(file);
      else void onFile(file);
      return;
    }
    const payload = e.dataTransfer.getData(DRAG_MIME);
    if (!payload || !background || !stage.current) return;
    const rect = stage.current.getBoundingClientRect();
    const at = { x: (e.clientX - rect.left) / zoom, y: (e.clientY - rect.top) / zoom };
    if (payload === 'text') addText(at);
    else addVariable(payload as VariableKey, at);
  };

  const editing = mode === 'edit';
  const selected = fields.find((f) => f.id === selectedId);

  return (
    <div
      ref={viewport}
      onPointerDown={onPointerDown}
      onDragOver={onDragOver}
      onDragLeave={(e) => e.currentTarget === e.target && setDragOver(false)}
      onDrop={onDrop}
      className={cn('relative min-h-0 min-w-0 flex-1 overflow-auto bg-workspace', panning && 'cursor-grab', dragOver && background && 'outline-2 -outline-offset-2 outline-dashed outline-accent')}
    >
      <div className="flex min-h-full w-max min-w-full items-center justify-center p-4 max-lg:pb-20 sm:p-12 sm:max-lg:pb-24">
        {!background ? (
          <EmptyDropzone onFile={(f) => void onFile(f)} dragOver={dragOver} />
        ) : (
          <div ref={stage} className="artboard-in relative shrink-0 shadow-artboard" style={{ width: canvas.width * zoom, height: canvas.height * zoom }}>
            {/* artboard at real image px, scaled with a transform */}
            <div className="absolute left-0 top-0 overflow-hidden bg-white" style={{ width: canvas.width, height: canvas.height, transform: `scale(${zoom})`, transformOrigin: '0 0' }}>
              <img src={background.url} alt="" draggable={false} className="absolute inset-0 size-full select-none" />
              {fields.map((f) => (
                <FieldVisual key={f.id} field={f} mode={mode} />
              ))}
            </div>

            {/* server render wiped over the preview to compare */}
            {mode === 'preview' && serverImage && (
              <>
                <img src={serverImage} alt="Server render" className="pointer-events-none absolute inset-0 size-full" style={{ clipPath: `inset(0 0 0 ${compare}%)` }} />
                <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${compare}%` }}>
                  <span className="absolute left-1.5 top-2 whitespace-nowrap rounded bg-accent px-1.5 py-0.5 text-[10px] font-semibold text-white">Server →</span>
                </div>
              </>
            )}

            {/* hit layer is in screen px so handles don't scale with zoom */}
            {editing && (
              <div role="group" aria-label={`Template canvas, ${canvas.width} by ${canvas.height}`} className="absolute inset-0">
                {fields.map((f) => (
                  <HitBox key={f.id} field={f} zoom={zoom} selected={f.id === selectedId} outlines={outlines} />
                ))}
                {selected && <SelectionFrame field={selected} zoom={zoom} />}
                <Guides zoom={zoom} width={canvas.width} height={canvas.height} />
              </div>
            )}

            {upload.status === 'uploading' && (
              <div className="absolute inset-x-0 bottom-0 h-1 bg-black/10" role="progressbar" aria-label="Uploading new image" aria-valuenow={Math.round(upload.progress * 100)}>
                <div className="h-full bg-accent transition-[width]" style={{ width: `${upload.progress * 100}%` }} />
              </div>
            )}
          </div>
        )}
      </div>

      <p id="canvas-help" className="sr-only">
        Arrow keys move the field, Shift for 10 pixels. Delete removes it. Escape deselects.
      </p>
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {upload.status === 'error' && background && (
        <div className="absolute inset-x-4 bottom-4 mx-auto max-w-md">
          <Notice
            level="error"
            action={
              upload.file && (
                <Button size="sm" variant="secondary" onClick={() => void onFile(upload.file!)}>
                  Retry
                </Button>
              )
            }
          >
            Upload failed: {upload.message}
          </Notice>
        </div>
      )}

      <ConfirmDialog
        open={!!pendingReplace}
        onOpenChange={(o) => !o && setPendingReplace(null)}
        title="Replace background?"
        description="Your fields stay where they are and are scaled to the new image."
        confirmLabel="Replace"
        onConfirm={() => {
          if (pendingReplace) void onFile(pendingReplace);
          setPendingReplace(null);
        }}
      />
    </div>
  );
}
