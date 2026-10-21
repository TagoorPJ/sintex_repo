import { Menu as BaseMenu } from '@base-ui/react/menu';
import type { ReactElement, ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface MenuProps {
  trigger: ReactElement;
  children: ReactNode;
  align?: 'start' | 'center' | 'end';
}

export function Menu({ trigger, children, align = 'end' }: MenuProps) {
  return (
    <BaseMenu.Root>
      <BaseMenu.Trigger render={trigger} />
      <BaseMenu.Portal>
        <BaseMenu.Positioner align={align} sideOffset={6} className="z-50">
          <BaseMenu.Popup className="pop min-w-48 rounded-xl border border-line bg-surface p-1 shadow-float outline-none">
            {children}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}

interface ItemProps {
  icon?: ReactNode;
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: 'default' | 'danger';
  hint?: string;
}

export function MenuItem({ icon, children, onClick, disabled, tone = 'default', hint }: ItemProps) {
  return (
    <BaseMenu.Item
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex h-9 cursor-default select-none items-center gap-2.5 rounded-lg px-2.5 text-sm outline-none [&_svg]:size-4',
        'data-[highlighted]:bg-sunken data-[disabled]:opacity-45',
        tone === 'danger' ? 'text-danger-text data-[highlighted]:bg-danger-subtle' : 'text-fg',
      )}
    >
      {icon}
      <span className="flex-1">{children}</span>
      {hint && <span className="text-xs text-fg-3">{hint}</span>}
    </BaseMenu.Item>
  );
}

export function MenuSeparator() {
  return <BaseMenu.Separator className="mx-1 my-1 h-px bg-line" />;
}
