import { Popover } from '@base-ui/react/popover';
import { Pipette } from 'lucide-react';
import { useId } from 'react';
import { HexColorInput, HexColorPicker } from 'react-colorful';
import { IconButton } from '@/components/ui/Button';
import { FieldLabel } from '@/components/ui/controls';
import { cn } from '@/lib/cn';
import { useEditor } from '../state';

const PRESETS = ['#FFFFFF', '#1F1F1F', '#D4A843', '#7A1F1F', '#0F5132', '#2D2B7E'];

interface EyeDropperResult {
  sRGBHex: string;
}
declare global {
  interface Window {
    EyeDropper?: new () => { open: () => Promise<EyeDropperResult> };
  }
}

function Swatch({ color, selected, onPick }: { color: string; selected: boolean; onPick: (c: string) => void }) {
  return (
    <button
      type="button"
      aria-label={color}
      aria-pressed={selected}
      onClick={() => onPick(color)}
      className={cn('size-6 rounded-md border border-black/10 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.2)]', selected && 'ring-2 ring-accent ring-offset-1 ring-offset-surface')}
      style={{ background: color }}
    />
  );
}

export function ColorField({ value, onChange, label = 'Color' }: { value: string; onChange: (hex: string, final: boolean) => void; label?: string }) {
  const id = useId();
  const palette = useEditor((s) => s.analysis?.palette ?? []);
  const pick = (c: string) => onChange(c.toUpperCase(), true);
  const eyedropper = typeof window !== 'undefined' && !!window.EyeDropper;

  return (
    <div>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Popover.Root>
        <Popover.Trigger
          id={id}
          className="flex h-8 w-full items-center gap-2 rounded-lg border border-line-strong bg-surface px-2 text-[13px] text-fg hover:border-fg-3"
        >
          <span className="size-4 rounded border border-black/15" style={{ background: value }} />
          <span className="tabular uppercase">{value}</span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner side="left" align="start" sideOffset={8} collisionPadding={12} className="z-50">
            <Popover.Popup className="pop w-60 rounded-xl border border-line bg-surface p-3 shadow-float outline-none">
              {palette.length > 0 && (
                <>
                  <p className="mb-1.5 text-[11px] font-medium text-fg-3">From this image</p>
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {palette.map((c) => (
                      <Swatch key={c} color={c} selected={c === value} onPick={pick} />
                    ))}
                  </div>
                </>
              )}
              <p className="mb-1.5 text-[11px] font-medium text-fg-3">Presets</p>
              <div className="mb-3 flex flex-wrap gap-1.5">
                {PRESETS.map((c) => (
                  <Swatch key={c} color={c} selected={c === value} onPick={pick} />
                ))}
              </div>
              <div className="[&_.react-colorful]:!h-36 [&_.react-colorful]:!w-full">
                <HexColorPicker color={value} onChange={(c) => onChange(c.toUpperCase(), false)} />
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-[12px] text-fg-3">#</span>
                <HexColorInput
                  aria-label="Hex colour"
                  color={value}
                  onChange={(c) => onChange(c.toUpperCase(), true)}
                  className="h-8 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-2 text-[13px] uppercase text-fg focus:border-accent focus:outline-none"
                />
                {eyedropper && (
                  <IconButton
                    label="Pick from image"
                    onClick={async () => {
                      try {
                        const r = await new window.EyeDropper!().open();
                        pick(r.sRGBHex);
                      } catch {
                        // user cancelled
                      }
                    }}
                  >
                    <Pipette />
                  </IconButton>
                )}
              </div>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}
