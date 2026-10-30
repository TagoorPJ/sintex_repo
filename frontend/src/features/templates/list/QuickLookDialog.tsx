import { Pencil } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Button } from '@/components/ui/Button';
import { Segmented } from '@/components/ui/controls';
import { Modal } from '@/components/ui/Dialog';
import type { Template } from '../model/types';
import { SCENARIOS, type Scenario } from '../model/variables';
import { ScaledStage, StaticRender } from '../render/StaticRender';

type QuickScenario = Exclude<Scenario, 'custom'>;

export function QuickLookDialog({ template, onClose }: { template: Template | null; onClose: () => void }) {
  const [scenario, setScenario] = useState<QuickScenario>('typical');
  const navigate = useNavigate();
  return (
    <Modal
      open={!!template}
      onOpenChange={(o) => !o && onClose()}
      title={template?.name ?? ''}
      description="How the greeting looks with sample values."
      size="lg"
      footer={
        template && (
          <Button variant="primary" icon={<Pencil className="size-4" />} onClick={() => navigate(`/templates/${template.id}`)}>
            Edit template
          </Button>
        )
      }
    >
      {template && (
        <div className="flex flex-col items-center gap-4">
          <Segmented
            ariaLabel="Sample values"
            value={scenario}
            onChange={setScenario}
            options={(Object.keys(SCENARIOS) as QuickScenario[]).map((k) => ({ value: k, label: SCENARIOS[k].label }))}
          />
          <ScaledStage canvas={template.canvas} maxHeight={Math.min(560, window.innerHeight - 260)} className="w-full">
            <StaticRender canvas={template.canvas} backgroundUrl={template.background?.url ?? null} fields={template.fields} values={SCENARIOS[scenario].values} />
          </ScaledStage>
        </div>
      )}
    </Modal>
  );
}
