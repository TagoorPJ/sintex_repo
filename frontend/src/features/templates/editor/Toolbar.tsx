import { ArrowLeft, ChevronDown, Eye, Loader2, Magnet, Maximize, Minus, PanelLeft, PenLine, Plus, Redo2, Save, ScanEye, Undo2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button, IconButton } from '@/components/ui/Button';
import { Menu, MenuItem, MenuSeparator } from '@/components/ui/Menu';
import { cn } from '@/lib/cn';
import { TemplateStatus } from '../components/TemplateStatus';
import { relativeTime } from '../list/TemplateCard';
import { zoomStep } from './hooks';
import { docActions, effectiveZoom, useDoc, useEditor } from './state';

function SaveIndicator() {
  const dirty = useDoc((s) => s.dirty);
  const updatedAt = useDoc((s) => s.updatedAt);
  const templateId = useDoc((s) => s.templateId);
  const saveState = useEditor((s) => s.saveState);
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);

  let content: ReactNode;
  if (saveState === 'saving') content = <><Loader2 className="size-3 animate-spin" /> Saving…</>;
  else if (saveState === 'error') content = <span className="text-danger-text">Couldn't save</span>;
  else if (dirty) content = <><span className="size-1.5 rounded-full bg-warning" /> Unsaved changes</>;
  else if (templateId && updatedAt) content = <span title={new Date(updatedAt).toLocaleString()}>Saved · {relativeTime(updatedAt)}</span>;
  else content = <span>Not saved yet</span>;

  return (
    <span role="status" className="hidden items-center gap-1.5 whitespace-nowrap text-[12px] text-fg-3 lg:inline-flex">
      {content}
    </span>
  );
}

function NameField() {
  const name = useDoc((s) => s.doc.name);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  if (editing)
    return (
      <input
        autoFocus
        aria-label="Template name"
        value={draft}
        maxLength={80}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          docActions.setMeta({ name: draft.trim() || 'Untitled template' });
          setEditing(false);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
          if (e.key === 'Escape') {
            setDraft(name);
            setEditing(false);
          }
        }}
        className="h-8 w-56 min-w-0 rounded-lg border border-accent bg-surface px-2 text-sm font-semibold text-fg outline-none ring-2 ring-accent/25"
      />
    );
  return (
    <button
      type="button"
      onClick={() => {
        setDraft(name);
        setEditing(true);
      }}
      title="Rename"
      className="h-8 min-w-0 max-w-[16rem] truncate rounded-lg px-2 text-left text-sm font-semibold text-fg hover:bg-sunken"
    >
      {name}
    </button>
  );
}

interface Props {
  onSave: () => void;
  compact: boolean;
  phone: boolean;
}

export function Toolbar({ onSave, compact, phone }: Props) {
  const canUndo = useDoc((s) => s.past.length > 0);
  const canRedo = useDoc((s) => s.future.length > 0);
  const dirty = useDoc((s) => s.dirty);
  const status = useDoc((s) => s.status);
  const templateId = useDoc((s) => s.templateId);
  const hasBackground = useDoc((s) => !!s.doc.background);
  const mode = useEditor((s) => s.mode);
  const zoom = useEditor(effectiveZoom);
  const zoomSetting = useEditor((s) => s.zoom);
  const snapping = useEditor((s) => s.snapping);
  const outlines = useEditor((s) => s.showOutlines);
  const saveState = useEditor((s) => s.saveState);
  const set = useEditor((s) => s.set);
  const preview = mode === 'preview';

  return (
    <header className="flex h-13 shrink-0 items-center gap-1 border-b border-line bg-surface px-2 sm:gap-2 sm:px-3">
      <Link to="/templates" aria-label="Back to templates" className="touch-target inline-flex size-8 items-center justify-center rounded-lg text-fg-2 hover:bg-sunken hover:text-fg">
        <ArrowLeft className="size-4" />
      </Link>
      {compact && !preview && (
        <IconButton label="Fields and background" onClick={() => set({ leftOpen: !useEditor.getState().leftOpen })}>
          <PanelLeft />
        </IconButton>
      )}
      <div className="flex min-w-0 items-center gap-2">
        <NameField />
        <TemplateStatus status={status} className="hidden sm:inline-flex" />
        <SaveIndicator />
      </div>

      <div className="flex-1" />

      {!preview && !phone && (
        <>
          <div className="flex items-center">
            <IconButton label="Undo" shortcut="Ctrl+Z" disabled={!canUndo} onClick={() => useDoc.getState().undo()}>
              <Undo2 />
            </IconButton>
            <IconButton label="Redo" shortcut="Ctrl+Shift+Z" disabled={!canRedo} onClick={() => useDoc.getState().redo()}>
              <Redo2 />
            </IconButton>
          </div>
          <div className="mx-1 hidden h-5 w-px bg-line md:block" />
          <div className="hidden items-center md:flex">
            <IconButton label="Zoom out" shortcut="Ctrl+−" onClick={() => zoomStep(-1)} disabled={!hasBackground}>
              <Minus />
            </IconButton>
            <Menu
              align="center"
              trigger={
                <button type="button" aria-label="Zoom level" disabled={!hasBackground} className="tabular inline-flex h-8 w-16 items-center justify-center gap-0.5 rounded-lg text-[12px] font-medium text-fg-2 hover:bg-sunken disabled:opacity-40">
                  {zoomSetting === 'fit' ? 'Fit' : `${Math.round(zoom * 100)}%`}
                  <ChevronDown className="size-3" />
                </button>
              }
            >
              <MenuItem icon={<Maximize />} hint="Ctrl+0" onClick={() => set({ zoom: 'fit' })}>
                Fit to screen
              </MenuItem>
              {[0.5, 1, 2].map((z) => (
                <MenuItem key={z} onClick={() => set({ zoom: z })}>
                  {z * 100}%
                </MenuItem>
              ))}
              <MenuSeparator />
              <MenuItem icon={<Magnet />} hint={snapping ? 'On' : 'Off'} onClick={() => set({ snapping: !snapping })}>
                Snapping
              </MenuItem>
              <MenuItem icon={<ScanEye />} hint={outlines ? 'On' : 'Off'} onClick={() => set({ showOutlines: !outlines })}>
                Field outlines
              </MenuItem>
            </Menu>
            <IconButton label="Zoom in" shortcut="Ctrl++" onClick={() => zoomStep(1)} disabled={!hasBackground}>
              <Plus />
            </IconButton>
          </div>
          <div className="mx-1 hidden h-5 w-px bg-line md:block" />
        </>
      )}

      <ThemeToggle />
      {!phone && (
        <Button
          size="sm"
          variant={preview ? 'subtle' : 'ghost'}
          icon={preview ? <PenLine className="size-4" /> : <Eye className="size-4" />}
          onClick={() => set({ mode: preview ? 'edit' : 'preview', selectedId: null })}
          disabled={!hasBackground}
          aria-keyshortcuts="P"
        >
          <span className="hidden sm:inline">{preview ? 'Back to editing' : 'Preview'}</span>
        </Button>
      )}

      <Button
        size="sm"
        variant="primary"
        onClick={onSave}
        disabled={(!dirty && !!templateId && saveState !== 'error') || saveState === 'saving'}
        className={cn('min-w-24', compact && 'min-w-0')}
        aria-keyshortcuts="Control+S"
      >
        {saveState === 'saving' ? (
          <>
            <Loader2 className="size-4 animate-spin" /> Saving…
          </>
        ) : saveState === 'saved' ? (
          <>
            <svg className="check-draw size-4 text-success-text" viewBox="0 0 16 16" fill="none" aria-hidden>
              <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Saved
          </>
        ) : (
          <>
            <Save className="size-4" /> Save
          </>
        )}
      </Button>

    </header>
  );
}
