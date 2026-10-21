import { Dialog as BaseDialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import type { ReactNode, RefObject } from 'react';
import { cn } from '@/lib/cn';
import { Button } from './Button';

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  initialFocus?: RefObject<HTMLElement | null>;
  dismissible?: boolean;
}

const widths = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-2xl', xl: 'max-w-5xl' };

// focus trapped, goes back to the trigger on close
export function Modal({ open, onOpenChange, title, description, children, footer, size = 'md', initialFocus, dismissible = true }: ModalProps) {
  return (
    <BaseDialog.Root open={open} onOpenChange={(o) => onOpenChange(o)} disablePointerDismissal={!dismissible}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className="backdrop fixed inset-0 z-50 bg-[rgb(15_23_42/0.4)]" />
        <BaseDialog.Popup
          initialFocus={initialFocus}
          className={cn(
            'pop fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-32px)] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-line bg-surface shadow-dialog outline-none',
            widths[size],
          )}
          style={{ transformOrigin: 'center' }}
        >
          <div className={cn('px-5 pb-2 pt-5', dismissible && 'pr-14')}>
            <BaseDialog.Title className="text-lg font-semibold text-fg">{title}</BaseDialog.Title>
            {description && <BaseDialog.Description className="mt-1 text-sm text-fg-2">{description}</BaseDialog.Description>}
          </div>
          {children && <div className="min-h-0 flex-1 overflow-auto px-5 py-2">{children}</div>}
          {footer && <div className="flex flex-wrap items-center justify-end gap-2 px-5 pb-5 pt-3">{footer}</div>}
          {/* last in the DOM so initial focus lands on content, not the close button */}
          {dismissible && (
            <BaseDialog.Close aria-label="Close" className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-lg text-fg-3 hover:bg-sunken hover:text-fg">
              <X className="size-4" />
            </BaseDialog.Close>
          )}
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}

interface ConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel: string;
  tone?: 'primary' | 'danger';
  loading?: boolean;
  onConfirm: () => void;
  children?: ReactNode;
  confirmIcon?: ReactNode;
  confirmDisabled?: boolean;
}

// focus starts on Cancel since that's the safe option
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, tone = 'primary', loading, onConfirm, children, confirmIcon, confirmDisabled }: ConfirmProps) {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <BaseDialog.Close render={<Button variant="secondary">Cancel</Button>} />
          <Button variant={tone === 'danger' ? 'danger' : 'primary'} loading={loading} onClick={onConfirm} icon={confirmIcon} disabled={confirmDisabled}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Modal>
  );
}
