import { create } from 'zustand';
import type { Guide, GapGuide } from '../model/geometry';
import type { ImageAnalysis, ImageNotice } from '../model/image';
import type { Asset, Box, Canvas, Fit, Template, TemplateStatus, TextField, TextStyle, Values, WhenEmpty } from '../model/types';
import type { Scenario } from '../model/variables';

// the editable part of a template, undo/redo only tracks this
export interface Doc {
  name: string;
  festivalId: string | null;
  canvas: Canvas;
  background: Asset | null;
  fields: TextField[];
}

export type FieldPatch = Partial<Pick<TextField, 'text' | 'label'>> & {
  box?: Partial<Box>;
  style?: Partial<TextStyle>;
  fit?: Partial<Fit>;
  whenEmpty?: Partial<WhenEmpty>;
};

const HISTORY_LIMIT = 100;
const COALESCE_MS = 500;

export const emptyDoc = (): Doc => ({ name: 'Untitled template', festivalId: null, canvas: { width: 1080, height: 1620 }, background: null, fields: [] });

interface DocState {
  doc: Doc;
  past: Doc[];
  future: Doc[];
  lastKey: string | null;
  lastAt: number;
  savedJson: string;
  dirty: boolean;
  templateId: string | null;
  version: number;
  status: TemplateStatus;
  updatedAt: string | null;
  load: (t: Template | null, overrides?: Partial<Doc>) => void;
  // same key within 500ms merges into one undo step
  commit: (fn: (d: Doc) => Doc, key?: string) => void;
  undo: () => void;
  redo: () => void;
  markSaved: (t: Template, sentJson: string) => void;
  setStatus: (status: TemplateStatus) => void;
  replaceDoc: (doc: Doc) => void;
}

export const json = (d: Doc) => JSON.stringify(d);

export function normalizeField(f: TextField): TextField {
  return {
    ...f,
    box: {
      x: Number(f.box?.x ?? 0),
      y: Number(f.box?.y ?? 0),
      width: Math.max(1, Number(f.box?.width ?? 200)),
    },
    style: {
      fontFamily: f.style?.fontFamily ?? 'poppins',
      fontWeight: f.style?.fontWeight ?? 500,
      fontSize: Number(f.style?.fontSize ?? 36),
      color: f.style?.color ?? '#FFFFFF',
      align: f.style?.align ?? 'center',
      letterSpacing: Number(f.style?.letterSpacing ?? 0),
      lineHeight: Number(f.style?.lineHeight ?? 1.2),
      textCase: f.style?.textCase ?? 'none',
      shadow: Boolean(f.style?.shadow),
    },
    fit: {
      minFontSize: Number(f.fit?.minFontSize ?? 18),
      maxLines: (f.fit?.maxLines ?? 1) as 1 | 2,
    },
    whenEmpty: {
      mode: f.whenEmpty?.mode ?? 'hide',
      text: f.whenEmpty?.text ?? '',
    },
  };
}

export function docFromTemplate(t: Template): Doc {
  return {
    name: t.name,
    festivalId: t.festivalId,
    canvas: {
      width: Number(t.canvas?.width ?? 1080),
      height: Number(t.canvas?.height ?? 1620),
    },
    background: t.background,
    fields: (t.fields ?? []).map(normalizeField),
  };
}

export const useDoc = create<DocState>((set, get) => ({
  doc: emptyDoc(),
  past: [],
  future: [],
  lastKey: null,
  lastAt: 0,
  savedJson: json(emptyDoc()),
  dirty: false,
  templateId: null,
  version: 0,
  status: 'draft',
  updatedAt: null,

  load: (t, overrides) => {
    const doc = { ...(t ? docFromTemplate(t) : emptyDoc()), ...overrides };
    const saved = t ? json(docFromTemplate(t)) : json(emptyDoc());
    set({
      doc,
      past: [],
      future: [],
      lastKey: null,
      savedJson: saved,
      dirty: json(doc) !== saved,
      templateId: t?.id ?? null,
      version: t?.version ?? 0,
      status: t?.status ?? 'draft',
      updatedAt: t?.updatedAt ?? null,
    });
  },

  commit: (fn, key) => {
    const { doc, past, lastKey, lastAt, savedJson } = get();
    const next = fn(doc);
    if (next === doc) return;
    const now = performance.now();
    const merge = key !== undefined && key === lastKey && now - lastAt < COALESCE_MS;
    set({
      doc: next,
      past: merge ? past : [...past, doc].slice(-HISTORY_LIMIT),
      future: [],
      lastKey: key ?? null,
      lastAt: now,
      dirty: json(next) !== savedJson,
    });
  },

  undo: () => {
    const { past, doc, future, savedJson } = get();
    if (!past.length) return;
    const prev = past[past.length - 1];
    set({ doc: prev, past: past.slice(0, -1), future: [doc, ...future], lastKey: null, dirty: json(prev) !== savedJson });
  },

  redo: () => {
    const { past, doc, future, savedJson } = get();
    if (!future.length) return;
    const next = future[0];
    set({ doc: next, past: [...past, doc], future: future.slice(1), lastKey: null, dirty: json(next) !== savedJson });
  },

  markSaved: (t, sentJson) => {
    const { doc } = get();
    const serverDoc = docFromTemplate(t);
    const saved = json(serverDoc);
    // take the server copy (normalised colours, asset urls) unless the admin kept
    // editing while the save was in flight. history survives either way
    const next = json(doc) === sentJson ? serverDoc : doc;
    set({ doc: next, templateId: t.id, version: t.version, status: t.status, updatedAt: t.updatedAt, savedJson: saved, dirty: json(next) !== saved, lastKey: null });
  },

  setStatus: (status) => set({ status }),

  replaceDoc: (doc) => get().commit(() => doc),
}));

export function patchField(f: TextField, p: FieldPatch): TextField {
  return {
    ...f,
    ...('text' in p ? { text: p.text ?? null } : {}),
    ...('label' in p ? { label: p.label ?? null } : {}),
    box: p.box ? { ...f.box, ...p.box } : f.box,
    style: p.style ? { ...f.style, ...p.style } : f.style,
    fit: p.fit ? { ...f.fit, ...p.fit } : f.fit,
    whenEmpty: p.whenEmpty ? { ...f.whenEmpty, ...p.whenEmpty } : f.whenEmpty,
  };
}

export const docActions = {
  updateField(id: string, patch: FieldPatch, key?: string) {
    useDoc.getState().commit((d) => ({ ...d, fields: d.fields.map((f) => (f.id === id ? patchField(f, patch) : f)) }), key);
  },
  addField(field: TextField) {
    useDoc.getState().commit((d) => ({ ...d, fields: [...d.fields, field] }));
  },
  removeField(id: string) {
    useDoc.getState().commit((d) => ({ ...d, fields: d.fields.filter((f) => f.id !== id) }));
  },
  setFields(fields: TextField[]) {
    useDoc.getState().commit((d) => ({ ...d, fields }));
  },
  setMeta(patch: Partial<Pick<Doc, 'name' | 'festivalId'>>, key?: string) {
    useDoc.getState().commit((d) => ({ ...d, ...patch }), key);
  },
};

export type EditorMode = 'edit' | 'preview';

export interface UploadState {
  status: 'idle' | 'uploading' | 'error';
  progress: number;
  localUrl: string | null;
  fileName: string | null;
  message?: string;
  file?: File;
}

export type SaveState = 'idle' | 'saving' | 'saved' | 'error';

interface EditorState {
  selectedId: string | null;
  mode: EditorMode;
  zoom: 'fit' | number;
  fitScale: number;
  snapping: boolean;
  showOutlines: boolean;
  leftOpen: boolean; // flyout on small screens
  sheetOpen: boolean; // properties sheet on tablets
  scenario: Scenario;
  custom: Values;
  // edit mode only: {Name} placeholders vs sample text on canvas
  canvasText: 'tokens' | 'samples';
  analysis: ImageAnalysis | null;
  notices: ImageNotice[];
  upload: UploadState;
  saveState: SaveState;
  serverImage: string | null;
  compare: number; // wipe position 0-100 for the server compare
  announce: string;
  set: (patch: Partial<EditorState>) => void;
  select: (id: string | null) => void;
  reset: () => void;
}

const initialEditor = {
  selectedId: null,
  mode: 'edit' as EditorMode,
  zoom: 'fit' as const,
  fitScale: 0.4,
  snapping: true,
  showOutlines: true,
  leftOpen: false,
  sheetOpen: false,
  scenario: 'typical' as Scenario,
  custom: {},
  canvasText: 'tokens' as const,
  analysis: null,
  notices: [],
  upload: { status: 'idle', progress: 0, localUrl: null, fileName: null } as UploadState,
  saveState: 'idle' as SaveState,
  serverImage: null,
  compare: 50,
  announce: '',
};

export const useEditor = create<EditorState>((set) => ({
  ...initialEditor,
  set: (patch) => set(patch),
  select: (id) => set((s) => ({ selectedId: id, sheetOpen: id ? true : s.sheetOpen })),
  reset: () => set(initialEditor),
}));

export const effectiveZoom = (s: Pick<EditorState, 'zoom' | 'fitScale'>) => (s.zoom === 'fit' ? s.fitScale : s.zoom);

// live geometry while dragging/resizing. not in history, committed on release
export interface GestureState {
  fieldId: string | null;
  kind: 'move' | 'resize' | null;
  box: Box | null;
  fontSize: number | null;
  guides: Guide[];
  gaps: GapGuide[];
}

export const useGesture = create<GestureState>(() => ({ fieldId: null, kind: null, box: null, fontSize: null, guides: [], gaps: [] }));
export const clearGesture = () => useGesture.setState({ fieldId: null, kind: null, box: null, fontSize: null, guides: [], gaps: [] });
