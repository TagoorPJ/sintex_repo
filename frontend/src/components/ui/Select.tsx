import { Select as BaseSelect } from '@base-ui/react/select';
import { Check, ChevronDown } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface SelectOption<V extends string | number> {
  value: V;
  label: string;
  render?: ReactNode;
  hint?: string;
  style?: CSSProperties;
  disabled?: boolean;
}

interface Props<V extends string | number> {
  value: V | null;
  onChange: (value: V) => void;
  options: SelectOption<V>[];
  placeholder?: string;
  ariaLabel?: string;
  id?: string;
  className?: string;
  size?: 'sm' | 'md';
  footer?: ReactNode;
  triggerStyle?: CSSProperties;
}

export function Select<V extends string | number>({ value, onChange, options, placeholder = 'Select…', ariaLabel, id, className, size = 'sm', footer, triggerStyle }: Props<V>) {
  const items = Object.fromEntries(options.map((o) => [String(o.value), o.label]));
  return (
    <BaseSelect.Root
      value={value === null ? null : String(value)}
      items={items}
      onValueChange={(v) => {
        if (v === null) return;
        const opt = options.find((o) => String(o.value) === v);
        if (opt) onChange(opt.value);
      }}
    >
      <BaseSelect.Trigger
        id={id}
        aria-label={ariaLabel}
        style={triggerStyle}
        className={cn(
          'touch-target flex w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-line-strong bg-surface px-2.5 text-left text-[13px] text-fg hover:border-fg-3',
          'data-[popup-open]:border-accent',
          size === 'sm' ? 'h-8' : 'h-9 text-sm',
          className,
        )}
      >
        <BaseSelect.Value className="min-w-0 truncate data-[placeholder]:text-fg-3" placeholder={placeholder} />
        <BaseSelect.Icon className="shrink-0 text-fg-3">
          <ChevronDown className="size-4" />
        </BaseSelect.Icon>
      </BaseSelect.Trigger>
      <BaseSelect.Portal>
        <BaseSelect.Positioner sideOffset={4} alignItemWithTrigger={false} className="z-[55]">
          <BaseSelect.Popup className="pop max-h-[min(360px,var(--available-height))] min-w-(--anchor-width) overflow-y-auto rounded-xl border border-line bg-surface p-1 shadow-float outline-none">
            <BaseSelect.List>
              {options.map((o) => (
                <BaseSelect.Item
                  key={String(o.value)}
                  value={String(o.value)}
                  disabled={o.disabled}
                  className="flex min-h-8 cursor-default select-none items-center gap-2 rounded-lg py-1.5 pl-2 pr-2.5 text-[13px] text-fg outline-none data-[highlighted]:bg-sunken data-[disabled]:opacity-45"
                >
                  <span className="flex w-4 shrink-0 justify-center">
                    <BaseSelect.ItemIndicator>
                      <Check className="size-3.5 text-accent-strong" />
                    </BaseSelect.ItemIndicator>
                  </span>
                  <BaseSelect.ItemText style={o.style} className="flex-1 truncate">
                    {o.render ?? o.label}
                  </BaseSelect.ItemText>
                  {o.hint && <span className="text-xs text-fg-3">{o.hint}</span>}
                </BaseSelect.Item>
              ))}
            </BaseSelect.List>
            {footer && <div className="mt-1 border-t border-line pt-1">{footer}</div>}
          </BaseSelect.Popup>
        </BaseSelect.Positioner>
      </BaseSelect.Portal>
    </BaseSelect.Root>
  );
}
