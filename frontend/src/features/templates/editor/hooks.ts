import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { analyseImage, checkImage } from '../model/image';
import type { Template } from '../model/types';
import { keys } from '../queries';
import { missingForLive } from '../model/readiness';
import { isConflict, isFestivalTaken, store, StoreError } from '../store';
import { deleteSelected, nudge, setBackground } from './actions';
import { effectiveZoom, json, useDoc, useEditor, type Doc } from './state';

export function useImageUpload() {
  return useCallback(async (file: File) => {
    const ed = useEditor.getState();
    const checked = await checkImage(file);
    const error = checked.notices.find((n) => n.level === 'error');
    if (error) {
      ed.set({ notices: checked.notices });
      toast.error(error.message);
      return;
    }
    const localUrl = URL.createObjectURL(file);
    ed.set({ notices: checked.notices, upload: { status: 'uploading', progress: 0, localUrl, fileName: file.name, file } });
    try {
      const asset = await store.uploadImage(file, file.name, (progress) =>
        useEditor.setState((s) => ({ upload: { ...s.upload, progress } })),
      );
      setBackground(asset);
      useEditor.getState().set({ upload: { status: 'idle', progress: 1, localUrl: null, fileName: null } });
      URL.revokeObjectURL(localUrl);
    } catch (e) {
      useEditor.getState().set({
        upload: { status: 'error', progress: 0, localUrl, fileName: file.name, file, message: e instanceof Error ? e.message : 'Upload failed' },
      });
    }
  }, []);
}

// palette + luminance sampling for the current background
export function useBackgroundAnalysis() {
  const background = useDoc((s) => s.doc.background);
  const width = useDoc((s) => s.doc.canvas.width);
  useEffect(() => {
    if (!background) return;
    let cancelled = false;
    analyseImage(background.thumbnailUrl || background.url, width)
      .then((analysis) => !cancelled && useEditor.getState().set({ analysis }))
      .catch(() => !cancelled && useEditor.getState().set({ analysis: null }));
    return () => {
      cancelled = true;
    };
  }, [background, width]);
}

export interface Conflict {
  current: Template;
}

export function useTemplateSave() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [conflict, setConflict] = useState<Conflict | null>(null);
  const [festivalTaken, setFestivalTaken] = useState<{ templateName: string } | null>(null);
  const savedTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const save = useCallback(
    // named so the Retry toast can call it again
    async function doSave(opts: { versionOverride?: number; replaceFestival?: boolean; active?: boolean } = {}): Promise<Template | null> {
      const ed = useEditor.getState();
      if (ed.upload.status === 'uploading') {
        toast('Waiting for the image upload to finish…');
        return null;
      }
      const { doc, templateId, version } = useDoc.getState();
      const sent = json(doc);
      const input = { name: doc.name, festivalId: doc.festivalId, canvas: doc.canvas, backgroundAssetId: doc.background?.id ?? null, fields: doc.fields };
      ed.set({ saveState: 'saving' });
      try {
        const saveOpts = { replaceFestival: opts.replaceFestival, active: opts.active };
        const t = templateId
          ? await store.updateTemplate(templateId, input, opts.versionOverride ?? version, saveOpts)
          : await store.createTemplate(input, saveOpts);
        const wasLive = useDoc.getState().status === 'live';
        useDoc.getState().markSaved(t, sent);
        // saving publishes, so tell the admin what the chatbot will do now
        const missing = missingForLive(t);
        if (t.status === 'live' && (!wasLive || opts.replaceFestival)) toast.success('Saved. The chatbot now sends this greeting.');
        else if (t.status === 'inactive') toast('Saved. This template is switched off, so the chatbot does not use it.');
        else if (t.status === 'draft') toast(`Saved as a draft. To make it available to the chatbot, add ${missing.join(', ')}.`);
        qc.setQueryData(keys.template(t.id), t);
        void qc.invalidateQueries({ queryKey: keys.templates });
        void qc.invalidateQueries({ queryKey: keys.festivals });
        clearDraft(templateId);
        clearDraft(t.id);
        useEditor.getState().set({ saveState: 'saved' });
        clearTimeout(savedTimer.current);
        savedTimer.current = setTimeout(() => useEditor.getState().set({ saveState: 'idle' }), 1500);
        if (!templateId) navigate(`/templates/${t.id}`, { replace: true });
        return t;
      } catch (e) {
        useEditor.getState().set({ saveState: 'error' });
        if (isConflict(e) && e.extra.current) {
          setConflict({ current: e.extra.current as Template });
        } else if (isFestivalTaken(e)) {
          useEditor.getState().set({ saveState: 'idle' });
          setFestivalTaken({ templateName: String(e.extra.templateName ?? 'Another template') });
        } else {
          toast.error(`Couldn't save. ${e instanceof StoreError || e instanceof Error ? e.message : ''}`, {
            action: { label: 'Retry', onClick: () => void doSave(opts) },
          });
        }
        return null;
      }
    },
    [navigate, qc],
  );

  return { save, conflict, setConflict, festivalTaken, setFestivalTaken };
}

// local drafts for crash recovery
const draftKey = (id: string | null) => `greeting-draft:${id ?? 'new'}`;

export function clearDraft(id: string | null) {
  try {
    localStorage.removeItem(draftKey(id));
  } catch {
    // no storage, ignore
  }
}

export function readDraft(id: string | null): { doc: Doc; at: string } | null {
  try {
    return JSON.parse(localStorage.getItem(draftKey(id)) ?? 'null');
  } catch {
    return null;
  }
}

// mirror the dirty doc to localStorage (debounced 2s) so a crash or reload doesn't lose work
export function useDraftMirror() {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsub = useDoc.subscribe((s, prev) => {
      if (s.doc === prev.doc) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        const { dirty, doc, templateId } = useDoc.getState();
        try {
          if (dirty) localStorage.setItem(draftKey(templateId), JSON.stringify({ doc, at: new Date().toISOString() }));
          else localStorage.removeItem(draftKey(templateId));
        } catch {
          // quota or private mode, best effort only
        }
      }, 2000);
    });
    return () => {
      clearTimeout(timer);
      unsub();
    };
  }, []);
}

const ZOOM_STEPS = [0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];

export function zoomStep(direction: 1 | -1) {
  const ed = useEditor.getState();
  const z = effectiveZoom(ed);
  const next = direction > 0 ? ZOOM_STEPS.find((s) => s > z + 0.001) : [...ZOOM_STEPS].reverse().find((s) => s < z - 0.001);
  ed.set({ zoom: next ?? z });
}

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || !!el.closest('[role="listbox"],[role="menu"],[role="dialog"]');
}

export function useEditorShortcuts(onSave: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const ed = useEditor.getState();
      if (mod && e.key.toLowerCase() === 's') {
        e.preventDefault();
        onSave();
        return;
      }
      if (isTyping(e.target)) return;
      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) useDoc.getState().redo();
        else useDoc.getState().undo();
      } else if (mod && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        useDoc.getState().redo();
      } else if (mod && (e.key === '=' || e.key === '+')) {
        e.preventDefault();
        zoomStep(1);
      } else if (mod && e.key === '-') {
        e.preventDefault();
        zoomStep(-1);
      } else if (mod && e.key === '0') {
        e.preventDefault();
        ed.set({ zoom: 'fit' });
      } else if (!mod && (e.key === 'p' || e.key === 'P')) {
        ed.set({ mode: ed.mode === 'preview' ? 'edit' : 'preview' });
      } else if (e.key === 'Escape') {
        if (ed.mode === 'preview') ed.set({ mode: 'edit' });
        else ed.select(null);
      } else if (ed.mode === 'edit' && ed.selectedId) {
        const step = e.shiftKey ? 10 : 1;
        const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (moves[e.key]) {
          e.preventDefault();
          nudge(...moves[e.key]);
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault();
          deleteSelected();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onSave, enabled]);
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mql = window.matchMedia(query);
    const on = () => setMatches(mql.matches);
    mql.addEventListener('change', on);
    return () => mql.removeEventListener('change', on);
  }, [query]);
  return matches;
}
