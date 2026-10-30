import { useState } from 'react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { missingForLive } from '../model/readiness';
import type { Template } from '../model/types';
import { useSetActive } from '../queries';
import { isFestivalTaken } from '../store';

interface Pending {
  template: Template;
  festivalLabel: string;
  currentName: string;
}

// If another template already has this festival we confirm first, then turn that one off.
export function useActiveToggle(festivalLabelOf: (festivalId: string | null) => string | null, onChanged?: (t: Template) => void) {
  const setActive = useSetActive();
  const [pending, setPending] = useState<Pending | null>(null);

  const done = (t: Template, active: boolean) => {
    onChanged?.(t);
    if (!active) toast.success(`“${t.name}” is switched off. The chatbot no longer sends it.`);
    else if (t.status === 'live') toast.success(`“${t.name}” is active. The chatbot now sends it.`);
    else toast(`“${t.name}” is active but not used yet. It still needs ${missingForLive(t).join(', ')}.`);
  };

  const toggle = (t: Template, active: boolean, replaceFestival = false) =>
    setActive.mutate(
      { id: t.id, active, replaceFestival },
      {
        onSuccess: (saved) => done(saved, active),
        onError: (e) => {
          if (isFestivalTaken(e)) {
            setPending({ template: t, festivalLabel: festivalLabelOf(t.festivalId) ?? 'this festival', currentName: String(e.extra.templateName ?? 'Another template') });
          } else {
            toast.error(e instanceof Error ? e.message : "Couldn't change the template.");
          }
        },
      },
    );

  const dialog = (
    <ConfirmDialog
      open={!!pending}
      onOpenChange={(o) => !o && setPending(null)}
      title={`Make this the active ${pending?.festivalLabel ?? ''} greeting?`}
      description={`“${pending?.currentName}” is the active ${pending?.festivalLabel} greeting now. It will be switched off (you can switch it back on later).`}
      confirmLabel="Make active"
      loading={setActive.isPending}
      onConfirm={() => {
        if (pending) toggle(pending.template, true, true);
        setPending(null);
      }}
    />
  );

  return { toggle, dialog, busy: setActive.isPending };
}
