// the 3 values a WhatsApp user sends us. fixed by product, don't add more here
export type VariableKey = 'name' | 'number' | 'enterprise';
export const VARIABLE_KEYS: VariableKey[] = ['name', 'enterprise', 'number'];

// Server computes this. live: active + has festival, image and a field (chatbot uses it).
// draft: active but missing something. inactive: admin turned it off.
export type TemplateStatus = 'live' | 'draft' | 'inactive';
export type Align = 'left' | 'center' | 'right';
export type FontWeight = 400 | 500 | 600 | 700;
export type TextCase = 'none' | 'title' | 'upper';

export interface Box {
  x: number;
  y: number;
  width: number;
}

export interface TextStyle {
  fontFamily: string;
  fontWeight: FontWeight;
  fontSize: number;
  color: string;
  align: Align;
  letterSpacing: number; // em
  lineHeight: number;
  textCase: TextCase;
  shadow: boolean;
}

export interface Fit {
  minFontSize: number;
  maxLines: 1 | 2;
}

export interface WhenEmpty {
  mode: 'hide' | 'fallback';
  text: string;
}

// either a user variable or fixed text the admin typed
export interface TextField {
  id: string;
  kind: 'variable' | 'text';
  variable: VariableKey | null;
  text: string | null;
  label: string | null;
  box: Box;
  style: TextStyle;
  fit: Fit;
  whenEmpty: WhenEmpty;
}

export interface Canvas {
  width: number;
  height: number;
}

export interface Asset {
  id: string;
  url: string;
  thumbnailUrl: string;
  fileName: string;
  mimeType: string;
  bytes: number;
  width: number;
  height: number;
}

export interface Template {
  id: string;
  name: string;
  festivalId: string | null;
  status: TemplateStatus;
  /** admin on/off switch, max one active per festival */
  active: boolean;
  version: number;
  canvas: Canvas;
  background: Asset | null;
  fields: TextField[];
  createdAt: string;
  updatedAt: string;
  updatedBy: string | null;
}

export interface TemplateInput {
  name: string;
  festivalId: string | null;
  canvas: Canvas;
  backgroundAssetId: string | null;
  fields: TextField[];
}

export interface Festival {
  id: string;
  label: string;
  aliases: string[];
  nextDate: string | null;
  activeTemplateId: string | null;
}

export type Values = Partial<Record<VariableKey, string>>;
