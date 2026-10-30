import { CircleX, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export function Skeleton({ className }: { className?: string }) {
  // no shimmer on purpose
  return <div aria-hidden className={cn('rounded-lg bg-sunken', className)} />;
}

export function EmptyState({ icon, title, children, action, className }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('fade-in mx-auto flex max-w-md flex-col items-center px-6 py-14 text-center', className)}>
      <div className="mb-5">{icon}</div>
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      {children && <div className="mt-2 text-sm text-fg-2">{children}</div>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

const tones = {
  error: { cls: 'border-danger/30 bg-danger-subtle text-danger-text', Icon: CircleX },
  warning: { cls: 'border-warning/40 bg-warning-subtle text-warning-text', Icon: TriangleAlert },
  info: { cls: 'border-line bg-sunken text-fg-2', Icon: Info },
};

export function Notice({ level, children, action, className }: { level: keyof typeof tones; children: ReactNode; action?: ReactNode; className?: string }) {
  const { cls, Icon } = tones[level];
  return (
    <div role={level === 'error' ? 'alert' : undefined} className={cn('flex items-start gap-2 rounded-lg border px-3 py-2 text-[12px] leading-snug', cls, className)}>
      <Icon className="mt-px size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}
