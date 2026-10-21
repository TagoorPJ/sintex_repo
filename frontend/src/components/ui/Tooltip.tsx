import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';
import type { ReactElement, ReactNode } from 'react';

interface Props {
  label: ReactNode;
  shortcut?: string;
  side?: 'top' | 'bottom' | 'left' | 'right';
  children: ReactElement;
}

// shows on keyboard focus too. trigger keeps its own aria-label
export function Tooltip({ label, shortcut, side = 'bottom', children }: Props) {
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger render={children} />
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner side={side} sideOffset={6} className="z-[60]">
          <BaseTooltip.Popup className="pop flex items-center gap-2 rounded-lg bg-[#0f172a] px-2 py-1 text-xs font-medium text-white shadow-float dark:bg-[#e5e9f0] dark:text-[#0f172a]">
            {label}
            {shortcut && <kbd className="font-sans text-[11px] opacity-60">{shortcut}</kbd>}
          </BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}

export const TooltipProvider = BaseTooltip.Provider;
