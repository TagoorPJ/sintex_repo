import { ChevronDown, ChevronUp, Monitor, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useBlocker, useParams } from 'react-router';
import { Button, IconButton } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Dialog';
import { EmptyState, Skeleton } from '@/components/ui/feedback';
import { cn } from '@/lib/cn';
import { preloadDefaultFonts } from '../model/fonts';
import type { Template } from '../model/types';
import { fieldLabel } from '../model/variables';
import { useFestivals, useTemplate } from '../queries';
import { StoreError } from '../store';
import { CanvasTextToggle } from './canvas/CanvasTextToggle';
import { CanvasViewport } from './canvas/CanvasViewport';
import { readDraft, clearDraft, useBackgroundAnalysis, useDraftMirror, useEditorShortcuts, useMediaQuery, useTemplateSave } from './hooks';
import { FieldProperties } from './panels/FieldProperties';
import { LeftPanel } from './panels/LeftPanel';
import { PreviewPanel } from './panels/PreviewPanel';
import { TemplateProperties } from './panels/TemplateProperties';
import { docFromTemplate, json, useDoc, useEditor } from './state';
import { Toolbar } from './Toolbar';

function RightPanelContent({ onSave }: { onSave: () => Promise<unknown> }) {
  const mode = useEditor((s) => s.mode);
  const selectedId = useEditor((s) => s.selectedId);
  const field = useDoc((s) => s.doc.fields.find((f) => f.id === selectedId));
  if (mode === 'preview') return <PreviewPanel onSave={onSave} />;
  if (field) return <FieldProperties key={field.id} field={field} />;
  return <TemplateProperties />;
}

function EditorSkeleton() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-13 items-center gap-3 border-b border-line bg-surface px-3">
        <Skeleton className="size-8" />
        <Skeleton className="h-5 w-40" />
        <div className="flex-1" />
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="hidden w-62 space-y-3 border-r border-line bg-surface p-4 xl:block">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
        <div className="flex flex-1 items-center justify-center bg-workspace">
          <Skeleton className="aspect-2/3 h-[70%] bg-surface" />
        </div>
        <div className="hidden w-74 space-y-3 border-l border-line bg-surface p-4 lg:block">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
      </div>
    </div>
  );
}

export function EditorPage() {
  const { id } = useParams();
  const isNew = !id || id === 'new';
  const query = useTemplate(isNew ? undefined : id);
  const festivals = useFestivals();

  const loadedFor = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [restore, setRestore] = useState<{ at: string } | null>(null);

  // load the doc once per template
  useEffect(() => {
    const key = isNew ? 'new' : id!;
    // a new template just got saved and the URL switched to /templates/:id, keep the undo history
    const justCreated = loadedFor.current === 'new' && !isNew && useDoc.getState().templateId === id;
    if (loadedFor.current === key || justCreated) {
      loadedFor.current = key;
      setReady(true);
      return;
    }
    if (!isNew && !query.data) return;
    loadedFor.current = key;
    useEditor.getState().reset();
    const t = isNew ? null : query.data!;
    useDoc.getState().load(t);
    const draft = readDraft(t?.id ?? null);
    // on purpose, this effect syncs the zustand stores with the route + loaded template
    // eslint-disable-next-line react/set-state-in-effect
    if (draft && (!t || draft.at > t.updatedAt) && json(draft.doc) !== json(t ? docFromTemplate(t) : useDoc.getState().doc)) setRestore({ at: draft.at });
    setReady(true);
  }, [id, isNew, query.data]);

  useEffect(() => {
    void preloadDefaultFonts();
  }, []);

  useBackgroundAnalysis();
  useDraftMirror();

  const { save, conflict, setConflict, festivalTaken, setFestivalTaken } = useTemplateSave();
  const requestSave = useCallback((): Promise<Template | null> => save(), [save]);

  const tablet = useMediaQuery('(max-width: 1023px)');
  const compact = useMediaQuery('(max-width: 1279px)');
  const phone = useMediaQuery('(max-width: 767px)');
  const leftOpen = useEditor((s) => s.leftOpen);
  const sheetOpen = useEditor((s) => s.sheetOpen);
  const mode = useEditor((s) => s.mode);
  const selectedId = useEditor((s) => s.selectedId);

  useEffect(() => {
    if (phone) useEditor.getState().set({ mode: 'preview', selectedId: null });
  }, [phone]);

  useEditorShortcuts(() => void requestSave(), ready && !phone);

  // warn about unsaved changes on in-app nav and tab close
  const blocker = useBlocker(({ currentLocation, nextLocation }) => useDoc.getState().dirty && currentLocation.pathname !== nextLocation.pathname && nextLocation.pathname !== `/templates/${useDoc.getState().templateId}`);
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (useDoc.getState().dirty) e.preventDefault();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);
  const [savingLeave, setSavingLeave] = useState(false);

  const doc = useDoc((s) => s.doc);
  const festivalLabel = festivals.data?.find((f) => f.id === doc.festivalId)?.label ?? 'this festival';

  if (!isNew && query.isError) {
    const notFound = query.error instanceof StoreError && query.error.status === 404;
    return (
      <EmptyState icon={<X className="size-10 text-fg-3" />} title={notFound ? "This template doesn't exist or was deleted." : "We couldn't load this template."} className="pt-24">
        <Link to="/templates" className="mt-4 inline-flex h-9 items-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg">
          Back to templates
        </Link>
      </EmptyState>
    );
  }
  if (!ready) return <EditorSkeleton />;

  const selectedField = doc.fields.find((f) => f.id === selectedId);
  const preview = mode === 'preview';

  return (
    // locked to the viewport, only the panels and canvas scroll
    <div className="relative flex h-dvh flex-col overflow-hidden bg-workspace">
      <Toolbar onSave={() => void requestSave()} compact={compact} phone={phone} />

      {restore && (
        <div className="flex items-center gap-3 border-b border-warning/40 bg-warning-subtle px-4 py-2 text-[13px] text-warning-text">
          <span className="flex-1">You have unsaved changes from {new Date(restore.at).toLocaleString()}. Restore them?</span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              const draft = readDraft(useDoc.getState().templateId);
              if (draft) useDoc.getState().replaceDoc(draft.doc);
              setRestore(null);
            }}
          >
            Restore
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              clearDraft(useDoc.getState().templateId);
              setRestore(null);
            }}
          >
            Discard
          </Button>
        </div>
      )}
      {phone && (
        <div className="flex items-center gap-2 border-b border-line bg-surface px-4 py-2 text-[12px] text-fg-2">
          <Monitor className="size-4 shrink-0" aria-hidden /> Designing works best on a tablet or computer. You can preview and rename here.
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        {/* left panel - column on desktop, flyout when compact, hidden in preview */}
        {!phone && (
          <aside
            aria-label="Fields and background"
            className={cn(
              'z-20 w-62 shrink-0 border-r border-line bg-surface transition-[margin,transform] duration-280 ease-out',
              compact ? 'absolute inset-y-0 left-0 shadow-float' : 'relative',
              compact && !leftOpen && '-translate-x-full shadow-none',
              !compact && preview && '-ml-62',
              compact && preview && 'hidden',
            )}
          >
            <LeftPanel />
          </aside>
        )}

        <main className="relative flex min-w-0 flex-1 flex-col" onPointerDown={() => compact && leftOpen && useEditor.getState().set({ leftOpen: false })}>
          <CanvasTextToggle />
          <CanvasViewport />
        </main>

        {/* right panel - column on desktop, bottom sheet on tablet/phone */}
        {!tablet ? (
          <aside aria-label={preview ? 'Preview' : 'Properties'} className="relative w-74 shrink-0 overflow-y-auto border-l border-line bg-surface">
            <RightPanelContent onSave={requestSave} />
          </aside>
        ) : (
          <aside
            aria-label={preview ? 'Preview' : 'Properties'}
            className={cn('absolute inset-x-0 bottom-0 z-30 flex flex-col rounded-t-2xl border-t border-line bg-surface shadow-dialog transition-[max-height] duration-280', sheetOpen ? 'max-h-[55%]' : 'max-h-12')}
          >
            <button
              type="button"
              aria-expanded={sheetOpen}
              onClick={() => useEditor.getState().set({ sheetOpen: !sheetOpen })}
              className="flex h-12 shrink-0 items-center gap-2 px-4 text-left text-[13px] font-medium text-fg"
            >
              <span className="absolute left-1/2 top-1.5 h-1 w-9 -translate-x-1/2 rounded-full bg-line-strong" aria-hidden />
              <span className="flex-1">{preview ? 'Sample values' : selectedField ? fieldLabel(selectedField) : 'Template'}</span>
              {sheetOpen ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
            </button>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <RightPanelContent onSave={requestSave} />
            </div>
          </aside>
        )}
      </div>

      <Modal
        open={!!festivalTaken}
        onOpenChange={(o) => !o && setFestivalTaken(null)}
        title={`Which ${festivalLabel} greeting should be active?`}
        description={`“${festivalTaken?.templateName ?? 'Another template'}” is the active ${festivalLabel} greeting. Only one template per festival can be active. You can switch between them any time.`}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setFestivalTaken(null)}>
              Cancel
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setFestivalTaken(null);
                void save({ active: false });
              }}
            >
              Save as inactive
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setFestivalTaken(null);
                void save({ replaceFestival: true, active: true });
              }}
            >
              Make this one active
            </Button>
          </>
        }
      />

      <Modal
        open={blocker.state === 'blocked'}
        onOpenChange={(o) => !o && blocker.state === 'blocked' && blocker.reset()}
        title="You have unsaved changes"
        description={`Leave without saving? Your changes to “${doc.name}” will be lost.`}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => blocker.state === 'blocked' && blocker.reset()}>
              Continue editing
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                clearDraft(useDoc.getState().templateId);
                if (blocker.state === 'blocked') blocker.proceed();
              }}
            >
              <span className="text-danger-text">Discard</span>
            </Button>
            <Button
              variant="primary"
              loading={savingLeave}
              onClick={async () => {
                setSavingLeave(true);
                const t = await save();
                setSavingLeave(false);
                if (t && blocker.state === 'blocked') blocker.proceed();
              }}
            >
              Save &amp; leave
            </Button>
          </>
        }
      />

      <Modal
        open={!!conflict}
        onOpenChange={(o) => !o && setConflict(null)}
        title="Someone else updated this template"
        description="Your copy is older than the saved one. Choose which version to keep."
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                if (conflict) useDoc.getState().load(conflict.current);
                setConflict(null);
              }}
            >
              Use their version
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                const v = conflict?.current.version;
                setConflict(null);
                void save({ versionOverride: v });
              }}
            >
              Overwrite with mine
            </Button>
          </>
        }
      />

      {compact && leftOpen && !phone && (
        <IconButton label="Close panel" className="absolute left-63 top-15 z-30 bg-surface shadow-float" onClick={() => useEditor.getState().set({ leftOpen: false })}>
          <X />
        </IconButton>
      )}
    </div>
  );
}
