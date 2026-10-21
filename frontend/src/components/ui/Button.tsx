import { Loader2 } from 'lucide-react';
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Tooltip } from './Tooltip';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle';
type Size = 'xs' | 'sm' | 'md' | 'icon';

const variants: Record<Variant, string> = {
  primary: 'bg-primary text-primary-fg hover:bg-primary-hover border border-transparent',
  secondary: 'bg-surface text-fg border border-line-strong hover:bg-hover',
  ghost: 'bg-transparent text-fg-2 hover:bg-sunken hover:text-fg border border-transparent',
  subtle: 'bg-sunken text-fg hover:bg-line border border-transparent',
  danger: 'bg-danger text-white hover:brightness-95 border border-transparent',
};

const sizes: Record<Size, string> = {
  xs: 'h-7 px-2 text-[12px] gap-1',
  sm: 'h-8 px-3 text-[13px] gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
  icon: 'size-8 p-0 [&_svg]:size-4',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'touch-target inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded-lg font-medium transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  shortcut?: string;
  size?: 'sm' | 'md';
  active?: boolean;
  tooltipSide?: 'top' | 'bottom' | 'left' | 'right';
  tone?: 'default' | 'danger';
}

// label is required, it's also used as the tooltip
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, shortcut, size = 'sm', active, tooltipSide, tone = 'default', className, children, type = 'button', ...rest },
  ref,
) {
  return (
    <Tooltip label={label} shortcut={shortcut} side={tooltipSide}>
      <button
        ref={ref}
        type={type}
        aria-label={label}
        aria-pressed={active}
        className={cn(
          'touch-target inline-flex shrink-0 items-center justify-center rounded-lg transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:size-4',
          size === 'sm' ? 'size-8' : 'size-9',
          active ? 'bg-accent-subtle text-accent-strong' : tone === 'danger' ? 'text-fg-2 hover:bg-danger-subtle hover:text-danger-text' : 'text-fg-2 hover:bg-sunken hover:text-fg',
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    </Tooltip>
  );
});
