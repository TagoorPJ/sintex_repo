import type { Canvas, TextField, TextStyle, Values, VariableKey } from './types';

export const VARIABLES: Record<VariableKey, { label: string; description: string; placeholder: string }> = {
  name: { label: 'Name', description: "Recipient's name", placeholder: 'Jithin Joy' },
  enterprise: { label: 'Enterprise Name', description: "Recipient's business name", placeholder: 'Welspun' },
  number: { label: 'Number', description: "Recipient's mobile number", placeholder: '9636542383' },
};

// default order from the reference design: name, enterprise, number
export const STACK_ORDER: VariableKey[] = ['name', 'enterprise', 'number'];

// Placeholders shown while designing. Real values come in per user from the chatbot,
// the admin never enters them.
export const TOKEN_VALUES: Values = { name: '{Name}', enterprise: '{Enterprise Name}', number: '{Number}' };

export type Scenario = 'typical' | 'long' | 'hindi' | 'empty' | 'custom';

export const SCENARIOS: Record<Exclude<Scenario, 'custom'>, { label: string; values: Values }> = {
  typical: { label: 'Typical', values: { name: 'Jithin Joy', number: '9636542383', enterprise: 'Welspun' } },
  long: {
    label: 'Long values',
    values: { name: 'Jithin Joy Kuruvilla Mathew', number: '+91 96365 42383', enterprise: 'Welspun India Limited' },
  },
  hindi: { label: 'Hindi', values: { name: 'जिथिन जॉय', number: '9636542383', enterprise: 'वेलस्पन' } },
  empty: { label: 'Empty', values: { name: '', number: '', enterprise: '' } },
};

export const MIN_FONT = 12;
export const MAX_FONT = 400;
export const MAX_TEXT_ELEMENTS = 10;

export const newId = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);

export function safeMargin(canvas: Canvas) {
  return Math.round(Math.min(canvas.width, canvas.height) * 0.04);
}

export function defaultStyle(canvas: Canvas, overrides: Partial<TextStyle> = {}): TextStyle {
  return {
    fontFamily: 'poppins',
    fontWeight: 700,
    fontSize: Math.round(canvas.width * 0.052),
    color: '#1F1F1F',
    align: 'center',
    letterSpacing: 0,
    lineHeight: 1.2,
    textCase: 'none',
    shadow: false,
    ...overrides,
  };
}

export function createField(
  canvas: Canvas,
  kind: TextField['kind'],
  variable: VariableKey | null,
  partial: Partial<TextField> = {},
): TextField {
  const style = partial.style ?? defaultStyle(canvas, kind === 'text' ? { fontWeight: 500, fontSize: Math.round(canvas.width * 0.037) } : {});
  const width = Math.round(canvas.width * 0.72);
  return {
    id: newId(),
    kind,
    variable: kind === 'variable' ? variable : null,
    text: kind === 'text' ? 'Warm Regards' : null,
    label: kind === 'text' ? 'Text' : null,
    box: { x: Math.round((canvas.width - width) / 2), y: Math.round(canvas.height * 0.82), width },
    style,
    fit: { minFontSize: Math.round(style.fontSize * 0.7), maxLines: 1 },
    whenEmpty: { mode: 'hide', text: '' },
    ...partial,
  };
}

export function fieldLabel(f: TextField): string {
  if (f.kind === 'variable' && f.variable) return VARIABLES[f.variable].label;
  return f.label?.trim() || 'Text';
}
