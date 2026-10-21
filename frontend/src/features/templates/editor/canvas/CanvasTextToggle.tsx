import { Segmented } from '@/components/ui/controls';
import { useDoc, useEditor } from '../state';

// floating switch over the canvas, {Name} placeholders or sample text
export function CanvasTextToggle() {
  const mode = useEditor((s) => s.mode);
  const canvasText = useEditor((s) => s.canvasText);
  const hasVariables = useDoc((s) => s.doc.fields.some((f) => f.kind === 'variable'));
  if (mode !== 'edit' || !hasVariables) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center">
      <div className="pointer-events-auto flex items-center gap-2 rounded-xl border border-line bg-surface/95 py-1 pl-3 pr-1 shadow-float backdrop-blur-sm">
        <span className="hidden text-[12px] text-fg-3 sm:inline">Show</span>
        <Segmented
          ariaLabel="Show on canvas"
          value={canvasText}
          onChange={(next) => useEditor.getState().set({ canvasText: next })}
          options={[
            { value: 'tokens', label: 'Field names' },
            { value: 'samples', label: 'Sample text' },
          ]}
        />
      </div>
    </div>
  );
}
