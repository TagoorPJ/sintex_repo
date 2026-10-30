import { AlignCenter, AlignHorizontalJustifyCenter, AlignLeft, AlignRight, AlignVerticalJustifyCenter, ChevronRight, Paintbrush, Trash2 } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Button, IconButton } from '@/components/ui/Button';
import { FieldLabel, NumberField, PanelSection, Segmented, Switch, TextInput, inputClass } from '@/components/ui/controls';
import { Notice } from '@/components/ui/feedback';
import { Select } from '@/components/ui/Select';
import { cn } from '@/lib/cn';
import { describe, fitCheck } from '../../model/fitCheck';
import { cssFamily, ensureFont, FONT_FAMILIES, getFamily } from '../../model/fonts';
import { fieldRect } from '../../model/geometry';
import { contrastRatio } from '../../model/image';
import { boxHeight } from '../../model/layout';
import type { FontWeight, TextField } from '../../model/types';
import { fieldLabel, MAX_FONT, MIN_FONT } from '../../model/variables';
import { applyStyleToAll, deleteSelected } from '../actions';
import { FieldIcon, VARIABLE_TINT } from '../canvas/CanvasViewport';
import { docActions, useDoc, useEditor, useGesture } from '../state';
import { ColorField } from './ColorField';

const WEIGHT_LABEL: Record<number, string> = { 400: 'Regular', 500: 'Medium', 600: 'Semi Bold', 700: 'Bold' };
const SELECTABLE_FONTS = FONT_FAMILIES.filter((f) => f.selectable);

export function FieldProperties({ field }: { field: TextField }) {
  // load one weight per family so the font menu renders each name in its own face
  useEffect(() => SELECTABLE_FONTS.forEach((f) => void ensureFont(f.id, f.weights.includes(400) ? 400 : f.weights[0])), []);
  const canvas = useDoc((s) => s.doc.canvas);
  const fields = useDoc((s) => s.doc.fields);
  const live = useGesture((s) => (s.fieldId === field.id ? s : null));
  const analysis = useEditor((s) => s.analysis);
  const box = live?.box ?? field.box;
  const h = boxHeight({ ...field.style, fontSize: live?.fontSize ?? field.style.fontSize }, field.fit.maxLines);
  const family = getFamily(field.style.fontFamily);
  const issues = useMemo(() => fitCheck(fields), [fields]);
  const myIssues = issues.byField.get(field.id) ?? [];
  const overlap = issues.overlaps.find((o) => o.a === field.id || o.b === field.id);

  const update = docActions.updateField;
  const id = field.id;
  const isVariable = field.kind === 'variable';

  const contrast = useMemo(() => {
    if (!analysis) return null;
    const r = fieldRect(field);
    return contrastRatio(field.style.color, analysis.sample(r.x, r.y, r.w, r.h));
  }, [analysis, field]);

  const setFontSize = (fontSize: number) => {
    const ratio = fontSize / field.style.fontSize;
    update(id, { style: { fontSize }, fit: { minFontSize: Math.max(8, Math.min(fontSize, Math.round(field.fit.minFontSize * ratio))) } });
  };

  return (
    <div className="fade-in">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <span className={cn('flex size-7 items-center justify-center rounded-md', isVariable && field.variable ? VARIABLE_TINT[field.variable] : 'bg-sunken text-fg-2')}>
          <FieldIcon field={field} className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[13px] font-semibold uppercase tracking-wide text-fg">{fieldLabel(field)}</h2>
          <p className="text-[11px] text-fg-3">{isVariable ? 'Filled in by the chatbot' : 'Your text, same on every card'}</p>
        </div>
        <IconButton label="Remove field" shortcut="Del" tone="danger" onClick={deleteSelected}>
          <Trash2 />
        </IconButton>
      </div>

      {(myIssues.length > 0 || overlap || (contrast !== null && contrast < 3)) && (
        <div className="space-y-1.5 border-b border-line px-4 py-3">
          {myIssues.map((i) => (
            <Notice key={i.scenario + i.overflow} level={i.overflow === 'truncated' ? 'error' : 'warning'}>
              {describe(i)}. {i.overflow === 'truncated' ? 'Widen the box, lower the minimum size or allow 2 lines.' : ''}
            </Notice>
          ))}
          {overlap && <Notice level="warning">Overlaps {overlap.labels.find((l) => l !== fieldLabel(field)) ?? overlap.labels[1]}.</Notice>}
          {contrast !== null && contrast < 3 && <Notice level="warning">Low contrast on this part of the image ({contrast.toFixed(1)}:1). Try another colour or turn on shadow.</Notice>}
        </div>
      )}

      {!isVariable && (
        <PanelSection title="Text">
          <FieldLabel htmlFor={`text-${id}`}>Text</FieldLabel>
          <textarea
            id={`text-${id}`}
            value={field.text ?? ''}
            maxLength={200}
            rows={2}
            onChange={(e) => update(id, { text: e.target.value }, `text:${id}`)}
            onBlur={(e) => !e.target.value.trim() && update(id, { text: 'Text' })}
            className={cn(inputClass, 'h-auto resize-y py-1.5')}
          />
          <div className="mt-3">
            <FieldLabel htmlFor={`label-${id}`} hint="only you see this">
              Layer name
            </FieldLabel>
            <TextInput id={`label-${id}`} value={field.label ?? ''} maxLength={40} placeholder="Text" onChange={(e) => update(id, { label: e.target.value }, `label:${id}`)} />
          </div>
        </PanelSection>
      )}

      <PanelSection title="Position & size">
        <div className="grid grid-cols-2 gap-2">
          <NumberField label="X" inlineLabel="X" value={Math.round(box.x)} min={0} max={canvas.width - box.width} onCommit={(x) => update(id, { box: { x } })} />
          <NumberField label="Y" inlineLabel="Y" value={Math.round(box.y)} min={0} max={Math.max(0, canvas.height - h)} onCommit={(y) => update(id, { box: { y } })} />
          <NumberField
            label="Width"
            inlineLabel="W"
            value={Math.round(box.width)}
            min={Math.max(48, field.style.fontSize * 2)}
            max={canvas.width - box.x}
            onCommit={(width) => update(id, { box: { width } })}
          />
          <div className="flex h-8 items-center rounded-lg bg-sunken px-2.5 text-[13px] text-fg-3" title="Height follows the text size and max lines">
            <span className="mr-2 text-[12px] font-medium">H</span>
            <span className="tabular">{Math.round(h)}</span>
            <span className="ml-auto text-[11px]">auto</span>
          </div>
        </div>
        <div className="mt-2 flex gap-1">
          <IconButton label="Centre horizontally on canvas" onClick={() => update(id, { box: { x: Math.round((canvas.width - field.box.width) / 2) } })}>
            <AlignHorizontalJustifyCenter />
          </IconButton>
          <IconButton label="Centre vertically on canvas" onClick={() => update(id, { box: { y: Math.round((canvas.height - h) / 2) } })}>
            <AlignVerticalJustifyCenter />
          </IconButton>
        </div>
      </PanelSection>

      <PanelSection title="Typography">
        <div className="space-y-3">
          <div>
            <FieldLabel>Font</FieldLabel>
            <Select
              ariaLabel="Font"
              value={field.style.fontFamily}
              triggerStyle={{ fontFamily: `${cssFamily(family.id)}, sans-serif` }}
              onChange={(fontFamily) => {
                const fam = getFamily(fontFamily);
                const weight = fam.weights.includes(field.style.fontWeight) ? field.style.fontWeight : fam.weights[fam.weights.length - 1];
                void ensureFont(fontFamily, weight);
                update(id, { style: { fontFamily, fontWeight: weight } });
              }}
              options={SELECTABLE_FONTS.map((f) => ({ value: f.id, label: f.label, hint: f.hint, style: { fontFamily: `${cssFamily(f.id)}, sans-serif`, fontSize: 15 } }))}
            />
          </div>
          <div className="grid grid-cols-[1fr_96px] gap-2">
            <div>
              <FieldLabel>Weight</FieldLabel>
              <Select<FontWeight>
                ariaLabel="Weight"
                value={field.style.fontWeight}
                onChange={(fontWeight) => update(id, { style: { fontWeight } })}
                options={family.weights.map((w) => ({ value: w, label: WEIGHT_LABEL[w] }))}
              />
            </div>
            <NumberField label="Size" value={Math.round(field.style.fontSize)} min={MIN_FONT} max={MAX_FONT} suffix="px" onCommit={setFontSize} />
          </div>
          <div className="flex items-end justify-between gap-2">
            <div>
              <FieldLabel>Align</FieldLabel>
              <Segmented
                ariaLabel="Text alignment"
                iconOnly
                value={field.style.align}
                onChange={(align) => update(id, { style: { align } })}
                options={[
                  { value: 'left', label: 'Align left', icon: <AlignLeft /> },
                  { value: 'center', label: 'Align centre', icon: <AlignCenter /> },
                  { value: 'right', label: 'Align right', icon: <AlignRight /> },
                ]}
              />
            </div>
            <div>
              <FieldLabel>Case</FieldLabel>
              <Segmented
                ariaLabel="Letter case"
                value={field.style.textCase}
                onChange={(textCase) => update(id, { style: { textCase } })}
                options={[
                  { value: 'none', label: 'Aa' },
                  { value: 'title', label: 'Title' },
                  { value: 'upper', label: 'AA' },
                ]}
              />
            </div>
          </div>
          <ColorField value={field.style.color} onChange={(color, final) => update(id, { style: { color } }, final ? undefined : `color:${id}`)} />
          <Switch checked={field.style.shadow} onChange={(shadow) => update(id, { style: { shadow } })} label="Shadow" description="Improves legibility on busy artwork" />
          {isVariable && (
            <Button size="sm" variant="ghost" className="w-full justify-start" icon={<Paintbrush className="size-3.5" />} onClick={() => applyStyleToAll(id)}>
              Apply this style to all fields
            </Button>
          )}
        </div>
      </PanelSection>

      {isVariable && (
        <PanelSection title="Long values">
          <div className="grid grid-cols-2 gap-2">
            <NumberField
              label="Shrink down to"
              value={Math.round(field.fit.minFontSize)}
              min={8}
              max={Math.round(field.style.fontSize)}
              suffix="px"
              onCommit={(minFontSize) => update(id, { fit: { minFontSize } })}
            />
            <div>
              <FieldLabel>Max lines</FieldLabel>
              <Segmented
                ariaLabel="Max lines"
                className="w-full"
                value={field.fit.maxLines}
                onChange={(maxLines) => update(id, { fit: { maxLines } })}
                options={[
                  { value: 1, label: '1' },
                  { value: 2, label: '2' },
                ]}
              />
            </div>
          </div>
          <p className="mt-2 text-[11px] text-fg-3">Too-long values shrink first, then {field.fit.maxLines === 2 ? 'wrap to a second line, then' : ''} end with “…”.</p>

          {field.variable === 'number' && (
            <p className="mt-3 text-[11px] text-fg-3">The number is printed exactly as the chatbot sends it, including its country code.</p>
          )}

          <div className="mt-3">
            <FieldLabel>If the value is empty</FieldLabel>
            <Segmented
              ariaLabel="If the value is empty"
              className="w-full"
              value={field.whenEmpty.mode}
              onChange={(mode) => update(id, { whenEmpty: { mode } })}
              options={[
                { value: 'hide', label: 'Hide field' },
                { value: 'fallback', label: 'Show text' },
              ]}
            />
            {field.whenEmpty.mode === 'fallback' && (
              <TextInput
                className="mt-2"
                aria-label="Fallback text"
                placeholder="e.g. Valued Partner"
                maxLength={80}
                value={field.whenEmpty.text}
                onChange={(e) => update(id, { whenEmpty: { text: e.target.value } }, `fallback:${id}`)}
              />
            )}
          </div>
        </PanelSection>
      )}

      <details className="group border-b border-line">
        <summary className="flex cursor-pointer list-none items-center gap-1 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-3 hover:text-fg">
          <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden /> Advanced
        </summary>
        <div className="grid grid-cols-2 gap-2 px-4 pb-4">
          <NumberField label="Letter spacing" value={field.style.letterSpacing} min={-0.1} max={0.5} step={0.01} precision={2} suffix="em" onCommit={(letterSpacing) => update(id, { style: { letterSpacing } })} />
          <NumberField label="Line height" value={field.style.lineHeight} min={0.8} max={2.5} step={0.05} precision={2} onCommit={(lineHeight) => update(id, { style: { lineHeight } })} />
        </div>
      </details>
    </div>
  );
}
