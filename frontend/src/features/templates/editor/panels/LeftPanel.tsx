import { Check, ImageOff, Plus, RefreshCw, Type } from 'lucide-react';
import { useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { PanelSection } from '@/components/ui/controls';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { Notice } from '@/components/ui/feedback';
import { cn } from '@/lib/cn';
import { ratioLabel } from '../../model/image';
import type { VariableKey } from '../../model/types';
import { fieldLabel, MAX_TEXT_ELEMENTS, STACK_ORDER, VARIABLES } from '../../model/variables';
import { addText, addVariable, removeBackground } from '../actions';
import { DRAG_MIME, FieldIcon, VARIABLE_ICON, VARIABLE_TINT } from '../canvas/CanvasViewport';
import { useImageUpload } from '../hooks';
import { useDoc, useEditor } from '../state';

const formatBytes = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);

function PaletteItem({ variable, disabled }: { variable: VariableKey; disabled: boolean }) {
  const placed = useDoc((s) => s.doc.fields.find((f) => f.kind === 'variable' && f.variable === variable));
  const selected = useEditor((s) => s.selectedId === placed?.id && !!placed);
  const meta = VARIABLES[variable];
  const Icon = VARIABLE_ICON[variable];
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        draggable={!disabled && !placed}
        onDragStart={(e) => {
          e.dataTransfer.setData(DRAG_MIME, variable);
          e.dataTransfer.effectAllowed = 'copy';
        }}
        onClick={() => addVariable(variable)}
        aria-label={placed ? `${meta.label}: placed. Select it` : `Add ${meta.label}`}
        className={cn(
          'group flex w-full items-center gap-3 rounded-lg border px-2.5 py-2 text-left transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-50',
          selected ? 'border-accent bg-accent-subtle' : 'border-line hover:border-line-strong hover:bg-hover',
          !placed && !disabled && 'cursor-grab active:cursor-grabbing',
        )}
      >
        <span className={cn('flex size-8 shrink-0 items-center justify-center rounded-lg', VARIABLE_TINT[variable])}>
          <Icon className="size-4" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-fg">{meta.label}</span>
          <span className="block truncate text-[11px] text-fg-3">{meta.description}</span>
        </span>
        {placed ? (
          <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-success-subtle text-success-text" title="Added">
            <Check className="size-3" aria-hidden />
          </span>
        ) : (
          <Plus className="size-4 text-fg-3 group-hover:text-fg" aria-hidden />
        )}
      </button>
    </li>
  );
}

export function LeftPanel() {
  const background = useDoc((s) => s.doc.background);
  const canvas = useDoc((s) => s.doc.canvas);
  const fields = useDoc((s) => s.doc.fields);
  const textFields = fields.filter((f) => f.kind === 'text');
  const hasFields = fields.length > 0;
  const selectedId = useEditor((s) => s.selectedId);
  const notices = useEditor((s) => s.notices);
  const onFile = useImageUpload();
  const input = useRef<HTMLInputElement>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const noImage = !background;

  return (
    // relative so the sr-only file input stays inside this scroller instead of stretching the page
    <div className="relative flex h-full flex-col overflow-y-auto">
      <PanelSection title="Fields">
        <p className="mb-2 text-[11px] text-fg-3">
          You don't type these. The chatbot sends each user's name, number and enterprise to the API, and they are printed here. Choose where they go: click to add, or drag onto the image.
        </p>
        <ul className="space-y-1.5">
          {STACK_ORDER.map((v) => (
            <PaletteItem key={v} variable={v} disabled={noImage} />
          ))}
        </ul>
        {/* under the list so buttons don't jump once the image loads */}
        {noImage && <p className="mt-2 text-[12px] text-fg-3">Upload an image first.</p>}
      </PanelSection>

      <PanelSection
        title="Fixed text"
        action={<span className="tabular text-[11px] text-fg-3">{textFields.length}/{MAX_TEXT_ELEMENTS}</span>}
      >
        <p className="mb-2 text-[11px] text-fg-3">Optional fixed text that is the same on every card, e.g. “Warm Regards”. Not for names.</p>
        <ul className="mb-2 space-y-1">
          {textFields.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                onClick={() => useEditor.getState().select(f.id)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px]',
                  selectedId === f.id ? 'bg-accent-subtle text-accent-strong' : 'text-fg hover:bg-hover',
                )}
              >
                <FieldIcon field={f} className="size-3.5 shrink-0 text-fg-3" />
                <span className="truncate">{f.text || fieldLabel(f)}</span>
              </button>
            </li>
          ))}
        </ul>
        <Button
          size="sm"
          variant="secondary"
          className="w-full"
          icon={<Type className="size-4" />}
          disabled={noImage || textFields.length >= MAX_TEXT_ELEMENTS}
          draggable={!noImage}
          onDragStart={(e) => e.dataTransfer.setData(DRAG_MIME, 'text')}
          onClick={() => addText()}
        >
          Add text
        </Button>
      </PanelSection>

      <PanelSection title="Background">
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} onChange={(e) => e.target.files?.[0] && void onFile(e.target.files[0])} />
        {background ? (
          <>
            <div className="flex gap-3">
              <img src={background.thumbnailUrl} alt="" className="h-20 w-16 shrink-0 rounded-md border border-line object-cover" />
              <div className="min-w-0 text-[12px]">
                <p className="truncate font-medium text-fg" title={background.fileName}>
                  {background.fileName}
                </p>
                <p className="tabular text-fg-2">
                  {canvas.width} × {canvas.height}
                </p>
                <p className="text-fg-3">{ratioLabel(canvas.width, canvas.height)}</p>
                <p className="text-fg-3">{formatBytes(background.bytes)}</p>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" className="flex-1" icon={<RefreshCw className="size-3.5" />} onClick={() => input.current?.click()}>
                Replace
              </Button>
              <Button size="sm" variant="ghost" icon={<ImageOff className="size-3.5" />} onClick={() => (hasFields ? setConfirmRemove(true) : removeBackground())}>
                Remove
              </Button>
            </div>
          </>
        ) : (
          <Button size="sm" variant="secondary" className="w-full" onClick={() => input.current?.click()}>
            Upload image
          </Button>
        )}
        {notices.filter((n) => n.level !== 'error').length > 0 && (
          <div className="mt-3 space-y-1.5">
            {notices
              .filter((n) => n.level !== 'error')
              .map((n) => (
                <Notice key={n.message} level={n.level}>
                  {n.message}
                </Notice>
              ))}
          </div>
        )}
      </PanelSection>

      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title="Remove background image?"
        description="Your fields are kept, so you can upload a different image."
        confirmLabel="Remove"
        tone="danger"
        onConfirm={() => {
          removeBackground();
          setConfirmRemove(false);
        }}
      />
    </div>
  );
}
