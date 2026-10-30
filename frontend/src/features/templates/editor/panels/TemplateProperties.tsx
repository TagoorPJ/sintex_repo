import { Check, CircleCheck, CircleDashed, Paintbrush, Plus, Rows3 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { FieldLabel, PanelSection, Switch, TextInput } from '@/components/ui/controls';
import { Modal } from '@/components/ui/Dialog';
import { cn } from '@/lib/cn';
import { ratioLabel } from '../../model/image';
import { Select } from '@/components/ui/Select';
import { fieldLabel, STACK_ORDER, VARIABLES } from '../../model/variables';
import { useActiveToggle } from '../../components/useActiveToggle';
import { missingForLive } from '../../model/readiness';
import { useCreateFestival, useFestivals, useTemplates } from '../../queries';
import { StoreError } from '../../store';
import { addVariable, applyStyleToAll, stackEvenly } from '../actions';
import { FieldIcon } from '../canvas/CanvasViewport';
import { docActions, useDoc, useEditor } from '../state';

function AddFestivalDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const [label, setLabel] = useState('');
  const [aliases, setAliases] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useCreateFestival();
  const submit = () => {
    setError(null);
    create.mutate(
      { label, aliases: aliases.split(',').map((a) => a.trim()).filter(Boolean) },
      {
        onSuccess: (f) => {
          onCreated(f.id);
          setLabel('');
          setAliases('');
          onClose();
        },
        onError: (e) => setError(e instanceof StoreError || e instanceof Error ? e.message : 'Could not add festival.'),
      },
    );
  };
  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Add festival"
      description="Festivals are shared by all templates. The chatbot matches users' words against the name and other names."
      size="sm"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} disabled={label.trim().length < 2} onClick={submit}>
            Add festival
          </Button>
        </>
      }
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (label.trim().length >= 2) submit();
        }}
      >
        <div>
          <FieldLabel htmlFor="fest-label">Name</FieldLabel>
          <TextInput id="fest-label" autoFocus value={label} maxLength={60} placeholder="e.g. Chhath Puja" onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div>
          <FieldLabel htmlFor="fest-aliases" hint="comma-separated">
            Other names
          </FieldLabel>
          <TextInput id="fest-aliases" value={aliases} placeholder="e.g. Chhath, Surya Shashthi" onChange={(e) => setAliases(e.target.value)} />
        </div>
        {error && <p className="text-[12px] text-danger-text">{error}</p>}
      </form>
    </Modal>
  );
}

export function TemplateProperties() {
  const name = useDoc((s) => s.doc.name);
  const festivalId = useDoc((s) => s.doc.festivalId);
  const canvas = useDoc((s) => s.doc.canvas);
  const fields = useDoc((s) => s.doc.fields);
  const hasBackground = useDoc((s) => !!s.doc.background);
  const festivals = useFestivals();
  const templates = useTemplates();
  const templateId = useDoc((s) => s.templateId);
  const savedStatus = useDoc((s) => s.status);
  const dirty = useDoc((s) => s.dirty);
  const background = useDoc((s) => s.doc.background);
  const missing = missingForLive({ festivalId, background, fields });
  // some other template already active for this festival, if any
  const owner = (fid: string) => templates.data?.find((t) => t.festivalId === fid && t.active && t.id !== templateId);
  const isActive = savedStatus !== 'inactive';
  const saved = templates.data?.find((t) => t.id === templateId);
  const activeToggle = useActiveToggle(
    (fid) => festivals.data?.find((f) => f.id === fid)?.label ?? null,
    (t) => useDoc.getState().setStatus(t.status),
  );
  const [adding, setAdding] = useState(false);
  const nameField = fields.find((f) => f.variable === 'name') ?? fields.find((f) => f.kind === 'variable');

  return (
    <div className="fade-in">
      <PanelSection title="Template">
        <div className="space-y-3">
          <div>
            <FieldLabel htmlFor="tpl-name">Name</FieldLabel>
            <TextInput id="tpl-name" value={name} maxLength={80} onChange={(e) => docActions.setMeta({ name: e.target.value }, 'name')} onBlur={(e) => !e.target.value.trim() && docActions.setMeta({ name: 'Untitled template' })} />
          </div>
          <div>
            <FieldLabel>Festival</FieldLabel>
            <Select
              ariaLabel="Festival"
              placeholder="Choose festival"
              value={festivalId}
              onChange={(id) => docActions.setMeta({ festivalId: id })}
              options={(festivals.data ?? []).map((f) => {
                const other = owner(f.id);
                return { value: f.id, label: f.label, hint: other ? `active: “${other.name.slice(0, 16)}”` : undefined };
              })}
              footer={
                <button type="button" onClick={() => setAdding(true)} className="flex h-8 w-full items-center gap-2 rounded-lg px-2 text-[13px] text-accent-strong hover:bg-sunken">
                  <Plus className="size-4" aria-hidden /> Add festival
                </button>
              }
            />
            {festivalId && owner(festivalId) && isActive ? (
              <p className="mt-1 text-[11px] text-warning-text">“{owner(festivalId)!.name}” is the active greeting for this festival. Saving will ask which one to keep active.</p>
            ) : (
              <p className="mt-1 text-[11px] text-fg-3">The chatbot sends this card when a user asks for this festival.</p>
            )}
          </div>
        </div>
      </PanelSection>

      <PanelSection title="Chatbot">
        <div className="mb-3">
          <Switch
            checked={isActive}
            onChange={(on) => saved && activeToggle.toggle(saved, on)}
            label="Active"
            description={
              !templateId
                ? 'New templates start active. Save first to switch it off.'
                : isActive
                  ? 'The chatbot can send this greeting.'
                  : 'Switched off. The chatbot does not use it.'
            }
          />
          {activeToggle.dialog}
        </div>
        {!isActive ? null : missing.length === 0 ? (
          <p className="flex items-start gap-2 text-[13px] text-success-text">
            <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            {savedStatus === 'live' && !dirty ? 'Live. The chatbot sends this greeting.' : 'Ready. It goes live when you save.'}
          </p>
        ) : (
          <div className="text-[13px]">
            <p className="flex items-start gap-2 text-fg-2">
              <CircleDashed className="mt-0.5 size-4 shrink-0" aria-hidden /> Not used by the chatbot yet. Needs:
            </p>
            <ul className="mt-1 list-disc pl-12 text-[12px] text-fg-3">
              {missing.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}
      </PanelSection>

      <PanelSection title="Canvas">
        <p className="tabular text-[13px] text-fg">
          {canvas.width} × {canvas.height} px
        </p>
        <p className="text-[12px] text-fg-3">{hasBackground ? ratioLabel(canvas.width, canvas.height) : 'Set by the background image'}</p>
      </PanelSection>

      <PanelSection title="Fields on this template" action={<span className="tabular text-[11px] text-fg-3">{fields.filter((f) => f.kind === 'variable').length} of 3</span>}>
        <ul className="space-y-0.5">
          {STACK_ORDER.map((v) => {
            const placed = fields.find((f) => f.variable === v);
            return (
              <li key={v} className="flex h-8 items-center gap-2 text-[13px]">
                {placed ? (
                  <button type="button" className="flex flex-1 items-center gap-2 rounded-md px-1 text-left hover:bg-hover" onClick={() => useEditor.getState().select(placed.id)}>
                    <FieldIcon field={placed} className="size-3.5 text-fg-3" />
                    <span className="flex-1">{VARIABLES[v].label}</span>
                    <Check className="size-3.5 text-success-text" aria-label="placed" />
                  </button>
                ) : (
                  <>
                    <span className="flex-1 px-1 text-fg-3">{VARIABLES[v].label}</span>
                    <Button size="xs" variant="ghost" disabled={!hasBackground} onClick={() => addVariable(v)}>
                      Add
                    </Button>
                  </>
                )}
              </li>
            );
          })}
          {fields
            .filter((f) => f.kind === 'text')
            .map((f) => (
              <li key={f.id}>
                <button type="button" className={cn('flex h-8 w-full items-center gap-2 rounded-md px-1 text-left text-[13px] hover:bg-hover')} onClick={() => useEditor.getState().select(f.id)}>
                  <FieldIcon field={f} className="size-3.5 text-fg-3" />
                  <span className="flex-1 truncate">{f.text || fieldLabel(f)}</span>
                  <span className="text-[11px] text-fg-3">text</span>
                </button>
              </li>
            ))}
        </ul>
        <div className="mt-3 grid gap-1.5">
          <Button size="sm" variant="secondary" icon={<Rows3 className="size-3.5" />} disabled={fields.length < 3} onClick={stackEvenly}>
            Stack fields evenly
          </Button>
          <Button size="sm" variant="ghost" icon={<Paintbrush className="size-3.5" />} disabled={!nameField || fields.filter((f) => f.kind === 'variable').length < 2} onClick={() => nameField && applyStyleToAll(nameField.id)}>
            Apply {nameField ? fieldLabel(nameField) : 'Name'}’s style to all
          </Button>
        </div>
      </PanelSection>

      <AddFestivalDialog
        open={adding}
        onClose={() => setAdding(false)}
        onCreated={(id) => {
          docActions.setMeta({ festivalId: id });
          toast.success('Festival added.');
        }}
      />
    </div>
  );
}
