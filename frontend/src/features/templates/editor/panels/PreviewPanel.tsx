import { CircleCheck, Copy, Download, Server, TriangleAlert } from 'lucide-react';
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { FieldLabel, PanelSection, Segmented, TextInput } from '@/components/ui/controls';
import { describe, fitCheck } from '../../model/fitCheck';
import type { Values, VariableKey } from '../../model/types';
import { SCENARIOS, STACK_ORDER, VARIABLES, type Scenario } from '../../model/variables';
import { downloadBlob, renderToBlob } from '../../render/renderToCanvas';
import { store } from '../../store';
import { currentValues } from '../actions';
import { useDoc, useEditor } from '../state';

interface Props {
  onSave: () => Promise<unknown>;
}

export function PreviewPanel({ onSave }: Props) {
  const fields = useDoc((s) => s.doc.fields);
  const doc = useDoc((s) => s.doc);
  const dirty = useDoc((s) => s.dirty);
  const templateId = useDoc((s) => s.templateId);
  const scenario = useEditor((s) => s.scenario);
  const custom = useEditor((s) => s.custom);
  const serverImage = useEditor((s) => s.serverImage);
  const compare = useEditor((s) => s.compare);
  const [request, setRequest] = useState<Record<string, unknown> | null>(null);
  const [testing, setTesting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const placed = STACK_ORDER.filter((v) => fields.some((f) => f.variable === v));
  const values: Values = scenario === 'custom' ? custom : SCENARIOS[scenario].values;
  const { issues, overlaps } = useMemo(() => fitCheck(fields), [fields]);

  const setValue = (key: VariableKey, value: string) => {
    useEditor.getState().set({ scenario: 'custom', custom: { ...values, [key]: value } });
  };

  const fix = (fieldId: string, s: Scenario) => useEditor.getState().set({ mode: 'edit', selectedId: fieldId, scenario: s, sheetOpen: true });

  const testServer = async () => {
    setTesting(true);
    try {
      let id = templateId;
      if (dirty || !id) {
        const saved = (await onSave()) as { id: string } | null;
        if (!saved) return;
        id = saved.id;
      }
      const r = await store.serverRender(id, currentValues());
      useEditor.getState().set({ serverImage: r.imageUrl, compare: 50 });
      setRequest(r.chatbotRequest);
    } catch (e) {
      toast.error(`Server render failed. ${e instanceof Error ? e.message : ''}`);
    } finally {
      setTesting(false);
    }
  };

  const downloadPng = async () => {
    setExporting(true);
    try {
      const blob = await renderToBlob(doc.canvas, doc.background?.url ?? null, doc.fields, currentValues());
      downloadBlob(blob, `${doc.name.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'greeting'}-preview.png`);
    } catch {
      toast.error("Couldn't create the image.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fade-in">
      <PanelSection title="Try sample values">
        <p className="mb-3 text-[12px] text-fg-3">
          Only for checking the design. For real users the chatbot sends their details to the API, and each user gets their own card.
        </p>
        <Segmented
          ariaLabel="Sample values"
          className="mb-4 flex w-full [&>button]:px-1"
          value={scenario}
          onChange={(s) => useEditor.getState().set({ scenario: s, custom: s === 'custom' ? values : custom })}
          options={[
            { value: 'typical', label: 'Typical' },
            { value: 'long', label: 'Long' },
            { value: 'hindi', label: 'Hindi' },
            { value: 'empty', label: 'Empty' },
            { value: 'custom', label: 'Custom' },
          ]}
        />
        {placed.length === 0 ? (
          <p className="text-[12px] text-fg-3">Add Name, Number or Enterprise Name to preview real values.</p>
        ) : (
          <div className="space-y-3">
            {placed.map((v) => (
              <div key={v}>
                <FieldLabel htmlFor={`pv-${v}`}>{VARIABLES[v].label}</FieldLabel>
                <TextInput id={`pv-${v}`} value={values[v] ?? ''} placeholder={VARIABLES[v].placeholder} onChange={(e) => setValue(v, e.target.value)} />
              </div>
            ))}
          </div>
        )}
      </PanelSection>

      <PanelSection title="Fit check">
        {issues.length === 0 && overlaps.length === 0 ? (
          <p className="flex items-center gap-2 text-[13px] text-success-text">
            <CircleCheck className="size-4" aria-hidden /> All fields fit with typical and long values.
          </p>
        ) : (
          <ul className="space-y-2">
            {issues.map((i) => (
              <li key={i.fieldId + i.scenario + i.overflow} className="flex items-start gap-2 text-[13px]">
                <TriangleAlert className={`mt-0.5 size-4 shrink-0 ${i.overflow === 'truncated' ? 'text-danger-text' : 'text-warning-text'}`} aria-hidden />
                <span className="flex-1 text-fg">{describe(i)}</span>
                <button type="button" className="text-[12px] font-medium text-accent-strong hover:underline" onClick={() => fix(i.fieldId, i.scenario)}>
                  Fix
                </button>
              </li>
            ))}
            {overlaps.map((o) => (
              <li key={o.a + o.b} className="flex items-start gap-2 text-[13px]">
                <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning-text" aria-hidden />
                <span className="flex-1 text-fg">
                  {o.labels[0]} overlaps {o.labels[1]}
                </span>
                <button type="button" className="text-[12px] font-medium text-accent-strong hover:underline" onClick={() => fix(o.a, 'typical')}>
                  Fix
                </button>
              </li>
            ))}
          </ul>
        )}
      </PanelSection>

      <PanelSection title="Check the final image">
        <div className="space-y-2">
          <Button size="sm" className="w-full" icon={<Download className="size-3.5" />} loading={exporting} onClick={() => void downloadPng()}>
            Download PNG
          </Button>
          <Button size="sm" className="w-full" icon={<Server className="size-3.5" />} loading={testing} onClick={() => void testServer()}>
            {dirty || !templateId ? 'Save & show the chatbot image' : 'Show the chatbot image'}
          </Button>
        </div>
        {serverImage && (
          <div className="mt-4">
            <FieldLabel htmlFor="compare" hint="editor ← → server">
              Compare
            </FieldLabel>
            <input id="compare" type="range" min={0} max={100} value={compare} onChange={(e) => useEditor.getState().set({ compare: Number(e.target.value) })} className="w-full accent-accent" />
            <Button size="sm" variant="ghost" className="mt-1" onClick={() => useEditor.getState().set({ serverImage: null })}>
              Hide server render
            </Button>
          </div>
        )}
        {request && (
          <div className="mt-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-medium text-fg-3">What the chatbot sends</span>
              <button
                type="button"
                aria-label="Copy request"
                className="inline-flex items-center gap-1 text-[11px] text-fg-3 hover:text-fg"
                onClick={() => void navigator.clipboard.writeText(JSON.stringify(request, null, 2)).then(() => toast.success('Copied.'))}
              >
                <Copy className="size-3" /> Copy
              </button>
            </div>
            <pre className="overflow-x-auto rounded-lg bg-sunken p-2 text-[11px] leading-relaxed text-fg">POST /api/greetings/render{'\n'}{JSON.stringify(request, null, 2)}</pre>
          </div>
        )}
      </PanelSection>
    </div>
  );
}
