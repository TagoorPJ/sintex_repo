import { Copy, EllipsisVertical, Eye, Pencil, Power, PowerOff, Trash2 } from 'lucide-react';
import { forwardRef } from 'react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/Button';
import { Menu, MenuItem, MenuSeparator } from '@/components/ui/Menu';
import { Tooltip } from '@/components/ui/Tooltip';
import { cn } from '@/lib/cn';
import { TemplateStatus } from '../components/TemplateStatus';
import { missingForLive } from '../model/readiness';
import type { Template } from '../model/types';
import { TOKEN_VALUES } from '../model/variables';
import { ScaledStage, StaticRender } from '../render/StaticRender';

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), 'minute');
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), 'hour');
  if (diff < 86400 * 30) return rtf.format(-Math.round(diff / 86400), 'day');
  return new Date(iso).toLocaleDateString();
}

interface Props {
  template: Template;
  festivalLabel: string | null;
  highlight?: boolean;
  onPreview: () => void;
  onDuplicate: () => void;
  onToggleActive: () => void;
  onDelete: () => void;
}

export const TemplateCard = forwardRef<HTMLElement, Props>(function TemplateCard(
  { template: t, festivalLabel, highlight, onPreview, onDuplicate, onToggleActive, onDelete },
  ref,
) {
  return (
    <article
      ref={ref}
      aria-label={t.name}
      className={cn(
        'group flex flex-col overflow-hidden rounded-xl border border-line bg-surface transition-[border-color,box-shadow] duration-150 hover:border-line-strong hover:shadow-[0_4px_12px_rgb(15_23_42/0.06)]',
        highlight && 'ring-2 ring-accent ring-offset-2 ring-offset-bg',
      )}
    >
      <button type="button" onClick={onPreview} aria-label={`Preview ${t.name}`} className="relative block aspect-4/5 w-full overflow-hidden bg-sunken p-3 text-left">
        {t.background ? (
          <ScaledStage canvas={t.canvas} contain className="size-full">
            <StaticRender canvas={t.canvas} backgroundUrl={t.background.thumbnailUrl} fields={t.fields} values={TOKEN_VALUES} />
          </ScaledStage>
        ) : (
          <div className="flex size-full items-center justify-center text-[13px] text-fg-3">No image yet</div>
        )}
        <TemplateStatus
          status={t.status}
          className="absolute left-2.5 top-2.5 shadow-sm"
          title={
            t.status === 'live'
              ? `The chatbot sends this for ${festivalLabel ?? 'its festival'}`
              : t.status === 'inactive'
                ? 'Switched off: the chatbot does not use it'
                : `Active, but not used yet. Needs ${missingForLive(t).join(', ')}.`
          }
        />
        <span className="absolute bottom-2.5 right-2.5 inline-flex items-center gap-1 rounded-full bg-[#0f172a]/80 px-2.5 py-1 text-[12px] font-medium text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
          <Eye className="size-3.5" aria-hidden /> Preview
        </span>
      </button>
      <div className="flex flex-1 flex-col gap-1 px-3 pb-3 pt-2.5">
        <Tooltip label={t.name} side="top">
          <h3 className="truncate text-sm font-semibold text-fg">{t.name}</h3>
        </Tooltip>
        <p className="truncate text-[12px] text-fg-2">
          {festivalLabel ?? <span className="text-warning-text">No festival</span>}
          <span className="text-fg-3"> · {t.canvas.width} × {t.canvas.height}</span>
        </p>
        <p className="text-[12px] text-fg-3" title={new Date(t.updatedAt).toLocaleString()}>
          Edited {relativeTime(t.updatedAt)}
        </p>
        <div className="mt-2 flex items-center justify-between gap-2">
          <Link
            to={`/templates/${t.id}`}
            className="touch-target inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-fg hover:bg-hover"
          >
            <Pencil className="size-3.5" aria-hidden /> Edit
          </Link>
          <Menu
            trigger={
              <Button variant="ghost" size="icon" aria-label={`More actions for ${t.name}`}>
                <EllipsisVertical className="size-4" />
              </Button>
            }
          >
            <MenuItem icon={<Eye />} onClick={onPreview}>
              Preview
            </MenuItem>
            <MenuItem icon={<Copy />} onClick={onDuplicate}>
              Duplicate
            </MenuItem>
            <MenuSeparator />
            {t.active ? (
              <MenuItem icon={<PowerOff />} onClick={onToggleActive}>
                Deactivate
              </MenuItem>
            ) : (
              <MenuItem icon={<Power />} onClick={onToggleActive}>
                Activate
              </MenuItem>
            )}
            <MenuSeparator />
            <MenuItem icon={<Trash2 />} tone="danger" onClick={onDelete}>
              Delete
            </MenuItem>
          </Menu>
        </div>
      </div>
    </article>
  );
});
