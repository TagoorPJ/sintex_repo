import { CircleCheck, CircleDashed, CirclePause } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { TemplateStatus as Status } from '../model/types';

const STATUS: Record<Status, { label: string; Icon: typeof CircleCheck; cls: string; title: string }> = {
  live: { label: 'Live', Icon: CircleCheck, cls: 'bg-success-subtle text-success-text border-success/30', title: 'Active: the chatbot sends this greeting' },
  draft: { label: 'Draft', Icon: CircleDashed, cls: 'bg-sunken text-fg-2 border-line', title: 'Active, but not complete yet' },
  inactive: { label: 'Inactive', Icon: CirclePause, cls: 'bg-warning-subtle text-warning-text border-warning/30', title: 'Switched off: the chatbot does not use it' },
};

// icon and label as well as colour, don't rely on colour alone
export function TemplateStatus({ status, className, title }: { status: Status; className?: string; title?: string }) {
  const { label, Icon, cls, title: defaultTitle } = STATUS[status];
  return (
    <span title={title ?? defaultTitle} className={cn('inline-flex h-5.5 items-center gap-1 rounded-full border px-2 text-[12px] font-medium', cls, className)}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}
