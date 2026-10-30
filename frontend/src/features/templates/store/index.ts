import { httpStore } from './httpStore';
import type { TemplateStore } from './types';

// chatbot reads templates from the same API
export const store: TemplateStore = httpStore;

export * from './types';
