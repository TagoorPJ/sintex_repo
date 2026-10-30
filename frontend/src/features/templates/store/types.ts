import type { Asset, Festival, Template, TemplateInput, Values } from '../model/types';

export interface ServerRender {
  imageUrl: string;
  chatbotRequest: Record<string, unknown>;
}

export interface SaveOptions {
  /** turn off whichever template currently holds this festival and activate this one */
  replaceFestival?: boolean;
  /** leave out to keep current value. new templates start active */
  active?: boolean;
}

// Implemented by httpStore. Heads up: saving an active template that has a festival,
// image and a field makes it live for the chatbot straight away.
export interface TemplateStore {
  listTemplates(): Promise<Template[]>;
  getTemplate(id: string): Promise<Template>;
  createTemplate(input: TemplateInput, opts?: SaveOptions): Promise<Template>;
  updateTemplate(id: string, input: TemplateInput, version: number, opts?: SaveOptions): Promise<Template>;
  deleteTemplate(id: string): Promise<void>;
  duplicateTemplate(id: string): Promise<Template>;
  setActive(id: string, active: boolean, opts?: { replaceFestival?: boolean }): Promise<Template>;
  uploadImage(file: Blob, fileName: string, onProgress?: (fraction: number) => void): Promise<Asset>;
  listFestivals(): Promise<Festival[]>;
  createFestival(input: { label: string; aliases: string[] }): Promise<Festival>;
  /** server render of the saved version, same image the chatbot would get */
  serverRender(id: string, values: Values): Promise<ServerRender>;
}

export class StoreError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export const isConflict = (e: unknown): e is StoreError => e instanceof StoreError && e.code === 'version_conflict';
export const isFestivalTaken = (e: unknown): e is StoreError => e instanceof StoreError && e.code === 'festival_taken';
