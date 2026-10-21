import { forwardRef, useEffect, useId, useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Tooltip } from './Tooltip';

export const inputClass =
  'h-8 w-full min-w-0 rounded-lg border border-line-strong bg-surface px-2.5 text-[13px] text-fg placeholder:text-fg-3 hover:border-fg-3 focus:border-accent focus:outline-none focus-visible:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-50';

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput({ className, ...rest }, ref) {
  return <input ref={ref} className={cn(inputClass, className)} {...rest} />;
});

export function FieldLabel({ htmlFor, children, hint }: { htmlFor?: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 flex items-baseline justify-between gap-2 text-xs font-medium text-fg-2">
      <span>{children}</span>
      {hint && <span className="font-normal text-fg-3">{hint}</span>}
    </label>
  );
}

export function PanelSection({ title, children, action, className }: { title: ReactNode; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <section className={cn('border-b border-line px-4 py-4 last:border-b-0', className)}>
      <div className="mb-3 flex min-h-5 items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-fg-3">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

// Segmented

export interface SegmentOption<V extends string | number> {
  value: V;
  label: string;
  icon?: ReactNode;
  count?: number;
}

interface SegmentedProps<V extends string | number> {
  value: V;
  onChange: (value: V) => void;
  options: SegmentOption<V>[];
  ariaLabel: string;
  iconOnly?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

// radio group that looks like a segmented control, arrow keys change selection
export function Segmented<V extends string | number>({ value, onChange, options, ariaLabel, iconOnly, size = 'sm', className }: SegmentedProps<V>) {
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = options.findIndex((o) => o.value === value);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      onChange(options[(i + 1) % options.length].value);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      onChange(options[(i - 1 + options.length) % options.length].value);
    }
  };
  return (
    // roving tabindex: group itself is only focusable from script, Tab goes to the selected radio
    <div role="radiogroup" aria-label={ariaLabel} tabIndex={-1} onKeyDown={onKeyDown} className={cn('inline-flex rounded-lg bg-sunken p-0.5 outline-none', className)}>
      {options.map((o) => {
        const selected = o.value === value;
        const button = (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={iconOnly ? o.label : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(o.value)}
            className={cn(
              'touch-target inline-flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors duration-100 [&_svg]:size-4',
              size === 'sm' ? 'h-7 px-2 text-[12px]' : 'h-8 px-3 text-[13px]',
              selected ? 'bg-surface text-fg shadow-[0_1px_2px_rgb(15_23_42/0.12)]' : 'text-fg-2 hover:text-fg',
            )}
          >
            {o.icon}
            {!iconOnly && o.label}
            {o.count !== undefined && <span className="tabular text-fg-3">{o.count}</span>}
          </button>
        );
        return iconOnly ? (
          <Tooltip key={String(o.value)} label={o.label}>
            {button}
          </Tooltip>
        ) : (
          button
        );
      })}
    </div>
  );
}

// NumberField

interface NumberFieldProps {
  label: string;
  value: number;
  onCommit: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  precision?: number;
  hideLabel?: boolean;
  disabled?: boolean;
  /** prefix inside the field, like "X" */
  inlineLabel?: string;
}

// Commits on Enter or blur. Up/Down arrows step, Shift for x10. Clamped values get a small hint.
export function NumberField({ label, value, onCommit, min = -Infinity, max = Infinity, step = 1, suffix, precision = 0, hideLabel, disabled, inlineLabel }: NumberFieldProps) {
  const id = useId();
  const format = (n: number) => (Number.isFinite(n) ? n.toFixed(precision).replace(/\.0+$/, '') : '');
  const [draft, setDraft] = useState(format(value));
  const [focused, setFocused] = useState(false);
  const [clampHint, setClampHint] = useState<string | null>(null);

  useEffect(() => {
    if (!focused) setDraft(format(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, focused]);

  const commit = (raw: string) => {
    const n = Number(raw.replace(',', '.'));
    if (raw.trim() === '' || Number.isNaN(n)) {
      setDraft(format(value));
      return;
    }
    const clamped = Math.min(max, Math.max(min, n));
    const rounded = Number(clamped.toFixed(precision));
    setClampHint(clamped !== n ? (n > max ? `max ${format(max)}` : `min ${format(min)}`) : null);
    setDraft(format(rounded));
    if (rounded !== value) onCommit(rounded);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      commit(draft);
      (e.target as HTMLInputElement).select();
    } else if (e.key === 'Escape') {
      setDraft(format(value));
      (e.target as HTMLInputElement).blur();
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const delta = (e.key === 'ArrowUp' ? 1 : -1) * step * (e.shiftKey ? 10 : 1);
      const next = Math.min(max, Math.max(min, Number(((Number(draft) || value) + delta).toFixed(precision))));
      setDraft(format(next));
      onCommit(next);
    }
  };

  return (
    <div className="min-w-0">
      {!hideLabel && !inlineLabel && <FieldLabel htmlFor={id}>{label}</FieldLabel>}
      <div className="relative">
        {inlineLabel && (
          <label htmlFor={id} className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-[12px] font-medium text-fg-3">
            {inlineLabel}
          </label>
        )}
        <input
          id={id}
          inputMode="decimal"
          aria-label={hideLabel || inlineLabel ? label : undefined}
          disabled={disabled}
          value={draft}
          onFocus={(e) => {
            setFocused(true);
            e.target.select();
          }}
          onBlur={() => {
            setFocused(false);
            commit(draft);
          }}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          className={cn(inputClass, 'tabular', inlineLabel && 'pl-7', suffix && 'pr-8')}
        />
        {suffix && <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-[12px] text-fg-3">{suffix}</span>}
      </div>
      <span role="status" className={cn('block text-[11px] text-warning-text', clampHint ? 'mt-1' : 'sr-only')}>
        {clampHint ?? ''}
      </span>
    </div>
  );
}

// Switch

export function Switch({ checked, onChange, label, description }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string }) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <label id={`${id}-label`} htmlFor={id} className="text-[13px] text-fg">
          {label}
        </label>
        {description && (
          <p id={`${id}-desc`} className="text-[11px] text-fg-3">
            {description}
          </p>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={description ? `${id}-desc` : undefined}
        onClick={() => onChange(!checked)}
        className={cn('relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150', checked ? 'bg-accent' : 'bg-line-strong')}
      >
        <span className={cn('inline-block size-4 rounded-full bg-white shadow transition-transform duration-150', checked ? 'translate-x-4.5' : 'translate-x-0.5')} />
      </button>
    </div>
  );
}
