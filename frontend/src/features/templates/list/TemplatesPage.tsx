import { AnimatePresence, motion } from 'motion/react';
import { useQueryClient } from '@tanstack/react-query';
import { LayoutTemplate, LogOut, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button, IconButton } from '@/components/ui/Button';
import { Segmented, TextInput } from '@/components/ui/controls';
import { ConfirmDialog } from '@/components/ui/Dialog';
import { EmptyState, Notice, Skeleton } from '@/components/ui/feedback';
import { Select } from '@/components/ui/Select';
import type { Template, TemplateStatus } from '../model/types';
import { useDeleteTemplate, useDuplicateTemplate, useFestivals, useTemplates } from '../queries';
import { useActiveToggle } from '../components/useActiveToggle';
import { logout } from '../store/httpStore';
import { QuickLookDialog } from './QuickLookDialog';
import { TemplateCard } from './TemplateCard';

type StatusFilter = 'all' | TemplateStatus;

function EmptyIllustration() {
  return (
    <svg width="120" height="96" viewBox="0 0 120 96" fill="none" aria-hidden>
      <rect x="22" y="14" width="56" height="72" rx="8" className="fill-sunken stroke-line-strong" strokeWidth="1.5" transform="rotate(-8 50 50)" />
      <rect x="42" y="10" width="56" height="72" rx="8" className="fill-surface stroke-line-strong" strokeWidth="1.5" transform="rotate(6 70 46)" />
      <rect x="32" y="12" width="56" height="72" rx="8" className="fill-surface stroke-fg-3" strokeWidth="1.5" />
      <path d="M60 34c3 5 7 8 7 13a7 7 0 0 1-14 0c0-5 4-8 7-13z" fill="var(--festive)" />
      <rect x="44" y="62" width="32" height="4" rx="2" className="fill-line-strong" />
      <rect x="50" y="70" width="20" height="3" rx="1.5" className="fill-line" />
    </svg>
  );
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const templates = useTemplates();
  const festivals = useFestivals();
  const duplicate = useDuplicateTemplate();
  const remove = useDeleteTemplate();
  const queryClient = useQueryClient();

  const [q, setQ] = useState('');
  const [festivalFilter, setFestivalFilter] = useState<string>('all');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [quickLook, setQuickLook] = useState<Template | null>(null);
  const [toDelete, setToDelete] = useState<Template | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [coverageOpen, setCoverageOpen] = useState(true);

  const festivalList = useMemo(() => festivals.data ?? [], [festivals.data]);
  const festivalLabel = (id: string | null) => festivalList.find((f) => f.id === id)?.label ?? null;
  const all = useMemo(() => templates.data ?? [], [templates.data]);
  const active = useActiveToggle(festivalLabel);

  const counts = useMemo(
    () => ({
      all: all.length,
      live: all.filter((t) => t.status === 'live').length,
      draft: all.filter((t) => t.status === 'draft').length,
      inactive: all.filter((t) => t.status === 'inactive').length,
    }),
    [all],
  );

  const filtered = all.filter((t) => {
    if (status !== 'all' && t.status !== status) return false;
    if (festivalFilter !== 'all' && t.festivalId !== festivalFilter) return false;
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      return t.name.toLowerCase().includes(needle) || (festivalLabel(t.festivalId) ?? '').toLowerCase().includes(needle);
    }
    return true;
  });

  const usedFestivals = festivalList.filter((f) => all.some((t) => t.festivalId === f.id));
  const covered = festivalList.filter((f) => f.activeTemplateId);
  const filtersActive = q.trim() !== '' || festivalFilter !== 'all' || status !== 'all';

  const onDuplicate = (t: Template) =>
    duplicate.mutate(t.id, {
      onSuccess: (copy) => {
        setHighlightId(copy.id);
        setTimeout(() => setHighlightId(null), 1400);
        toast.success(`Created “${copy.name}”.`, { action: { label: 'Open', onClick: () => navigate(`/templates/${copy.id}`) } });
      },
    });

  return (
    <div className="min-h-full bg-bg">
      <div className="mx-auto max-w-7xl px-4 pb-16 pt-6 sm:px-6 lg:px-8">
        {/* header */}
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <img
              src={`${import.meta.env.BASE_URL}brand/sintex-by-welspun.png`}
              alt="Sintex by Welspun"
              className="h-12 w-auto shrink-0 dark:box-content dark:rounded-lg dark:bg-white dark:p-1.5"
            />
            <div className="border-l border-line pl-4">
              <h1 className="text-2xl font-semibold tracking-tight text-fg">Greeting Templates</h1>
              <p className="mt-1 text-sm text-fg-2">Create and manage festive greeting cards for WhatsApp</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/templates/new"
              className="touch-target inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-fg hover:bg-primary-hover"
            >
              <Plus className="size-4" aria-hidden /> New template
            </Link>
            <div className="ml-1 flex items-center border-l border-line pl-2">
              <ThemeToggle size="md" />
              <IconButton
                label="Log out"
                size="md"
                onClick={() => {
                  queryClient.clear();
                  logout();
                }}
              >
                <LogOut />
              </IconButton>
            </div>
          </div>
        </header>

        {/* which festivals the chatbot can cover */}
        {all.length > 0 && usedFestivals.length > 0 && coverageOpen && (
          <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-line bg-surface px-4 py-2.5 text-[13px]">
            <span className="font-medium text-fg-2">Chatbot can send:</span>
            {covered.length === 0 && <span className="text-warning-text">No live templates yet</span>}
            {usedFestivals.map((f) =>
              f.activeTemplateId ? (
                <span key={f.id} className="inline-flex items-center gap-1 text-success-text">
                  ✓ {f.label}
                </span>
              ) : (
                <button key={f.id} type="button" onClick={() => setFestivalFilter(f.id)} className="text-fg-3 underline-offset-2 hover:text-fg hover:underline" title="Show templates for this festival">
                  — {f.label}
                </button>
              ),
            )}
            <button type="button" className="ml-auto text-fg-3 hover:text-fg" onClick={() => setCoverageOpen(false)} aria-label="Hide coverage">
              Hide
            </button>
          </div>
        )}

        {/* filters */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <div className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-fg-3" aria-hidden />
            <TextInput aria-label="Search templates" placeholder="Search templates" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 pl-8 text-sm" />
          </div>
          <div className="w-44">
            <Select
              size="md"
              ariaLabel="Festival"
              value={festivalFilter}
              onChange={setFestivalFilter}
              options={[{ value: 'all', label: 'All festivals' }, ...usedFestivals.map((f) => ({ value: f.id, label: f.label }))]}
            />
          </div>
          <Segmented
            size="md"
            ariaLabel="Status"
            value={status}
            onChange={setStatus}
            className="overflow-x-auto"
            options={[
              { value: 'all', label: 'All', count: counts.all },
              { value: 'live', label: 'Live', count: counts.live },
              { value: 'draft', label: 'Draft', count: counts.draft },
              { value: 'inactive', label: 'Inactive', count: counts.inactive },
            ]}
          />
        </div>

        {/* grid */}
        <div className="mt-5">
          {templates.isLoading ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(232px,1fr))] gap-5" aria-busy="true" aria-label="Loading templates">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="overflow-hidden rounded-xl border border-line bg-surface">
                  <Skeleton className="aspect-4/5 rounded-none" />
                  <div className="space-y-2 p-3">
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-3 w-1/2" />
                    <Skeleton className="mt-3 h-8 w-20" />
                  </div>
                </div>
              ))}
            </div>
          ) : templates.isError ? (
            <Notice
              level="error"
              action={
                <Button size="sm" variant="secondary" icon={<RefreshCw className="size-3.5" />} onClick={() => void templates.refetch()}>
                  Retry
                </Button>
              }
            >
              We couldn't load templates. {templates.error instanceof Error ? templates.error.message : ''}
            </Notice>
          ) : all.length === 0 ? (
            <EmptyState
              icon={<EmptyIllustration />}
              title="No greeting templates yet"
              action={
                <Link to="/templates/new" className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg hover:bg-primary-hover">
                  <Plus className="size-4" aria-hidden /> Create your first template
                </Link>
              }
            >
              Create a festive greeting card that WhatsApp users can receive with their name on it.
            </EmptyState>
          ) : filtered.length === 0 ? (
            <EmptyState icon={<LayoutTemplate className="size-10 text-fg-3" />} title={q.trim() ? `No templates match “${q.trim()}”` : 'No templates match these filters'}>
              {filtersActive && (
                <Button
                  className="mt-2"
                  variant="secondary"
                  onClick={() => {
                    setQ('');
                    setFestivalFilter('all');
                    setStatus('all');
                  }}
                >
                  Reset filters
                </Button>
              )}
            </EmptyState>
          ) : (
            <motion.ul layout className="grid grid-cols-[repeat(auto-fill,minmax(232px,1fr))] gap-5">
              <AnimatePresence initial={false} mode="popLayout">
                {filtered.map((t) => (
                  <motion.li
                    key={t.id}
                    layout
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.96 }}
                    transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
                    className="list-none"
                  >
                    <TemplateCard
                      template={t}
                      festivalLabel={festivalLabel(t.festivalId)}
                      highlight={highlightId === t.id}
                      onPreview={() => setQuickLook(t)}
                      onDuplicate={() => onDuplicate(t)}
                      onToggleActive={() => active.toggle(t, !t.active)}
                      onDelete={() => setToDelete(t)}
                    />
                  </motion.li>
                ))}
              </AnimatePresence>
            </motion.ul>
          )}
        </div>

      </div>

      <QuickLookDialog template={quickLook} onClose={() => setQuickLook(null)} />
      {active.dialog}

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`Delete “${toDelete?.name ?? ''}”?`}
        description={toDelete?.status === 'live' ? `WhatsApp users will no longer get a ${festivalLabel(toDelete.festivalId) ?? ''} greeting. This can't be undone.` : "This can't be undone."}
        confirmLabel="Delete"
        confirmIcon={<Trash2 className="size-4" />}
        tone="danger"
        onConfirm={() => {
          if (toDelete) remove.mutate(toDelete);
          setToDelete(null);
        }}
      />
    </div>
  );
}
