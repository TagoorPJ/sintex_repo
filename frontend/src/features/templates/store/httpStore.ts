import axios, { AxiosError } from 'axios';
import type { Asset, Festival, Template, TemplateInput } from '../model/types';
import { StoreError, type TemplateStore } from './types';

export function getApiBase(): string {
  if (typeof window !== 'undefined' && (window as any).__ENV__?.API_URL) {
    return (window as any).__ENV__.API_URL.replace(/\/$/, '');
  }
  const envUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');
  if (envUrl) return envUrl;
  if (typeof window !== 'undefined') {
    const p = window.location.pathname;
    const idx = p.indexOf('/studio');
    if (idx > 0) return p.slice(0, idx);
  }
  return '';
}

const API_BASE = getApiBase();
export const AUTH_KEY = 'greeting-admin';
export const AUTH_EVENT = 'greeting:auth-required';

export function getAuth(): { key: string; user: string } | null {
  try {
    return JSON.parse(sessionStorage.getItem(AUTH_KEY) ?? 'null');
  } catch {
    return null;
  }
}

export function setAuth(auth: { key: string; user: string } | null) {
  try {
    if (auth) sessionStorage.setItem(AUTH_KEY, JSON.stringify(auth));
    else sessionStorage.removeItem(AUTH_KEY);
  } catch {
    /* no storage, key only lives for this page */
  }
}

export const http = axios.create({ baseURL: API_BASE, timeout: 30000 });

http.interceptors.request.use((config) => {
  const auth = getAuth();
  if (auth?.key) config.headers.set('X-Admin-Key', auth.key);
  if (auth?.user) config.headers.set('X-Admin-User', auth.user);
  return config;
});

http.interceptors.response.use(
  (r) => r,
  (error: AxiosError<{ detail?: unknown }>) => {
    const status = error.response?.status ?? 0;
    const detail = error.response?.data?.detail;
    if (status === 401) window.dispatchEvent(new Event(AUTH_EVENT));
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'code' in detail) {
      const { code, message, ...extra } = detail as { code: string; message: string };
      return Promise.reject(new StoreError(status, code, message, extra));
    }
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      return Promise.reject(new StoreError(status, 'invalid', first?.msg ?? 'Invalid data'));
    }
    const message = status === 0 ? "Can't reach the server. Check your connection." : `Request failed (${status}).`;
    return Promise.reject(new StoreError(status, status === 0 ? 'offline' : 'http_error', message));
  },
);

const abs = (url: string) => (url.startsWith('/') ? `${API_BASE}${url}` : url);

function fixAsset(a: Asset): Asset {
  return { ...a, url: abs(a.url), thumbnailUrl: abs(a.thumbnailUrl) };
}

function fixTemplate(t: Template & { festivalLabel?: string | null }): Template {
  const { festivalLabel: _label, ...rest } = t;
  return { ...rest, background: t.background ? fixAsset(t.background) : null };
}

export const httpStore: TemplateStore = {
  async listTemplates() {
    const { data } = await http.get<Template[]>('/api/templates');
    return data.map(fixTemplate);
  },
  async getTemplate(id) {
    const { data } = await http.get<Template>(`/api/templates/${id}`);
    return fixTemplate(data);
  },
  async createTemplate(input: TemplateInput, opts) {
    const { data } = await http.post<Template>('/api/templates', { ...input, active: opts?.active ?? true, replaceFestival: !!opts?.replaceFestival });
    return fixTemplate(data);
  },
  async updateTemplate(id, input, version, opts) {
    try {
      const { data } = await http.put<Template>(`/api/templates/${id}`, { ...input, version, active: opts?.active, replaceFestival: !!opts?.replaceFestival });
      return fixTemplate(data);
    } catch (e) {
      if (e instanceof StoreError && e.code === 'version_conflict' && e.extra.current) {
        e.extra.current = fixTemplate(e.extra.current as Template);
      }
      throw e;
    }
  },
  async deleteTemplate(id) {
    await http.delete(`/api/templates/${id}`);
  },
  async duplicateTemplate(id) {
    const { data } = await http.post<Template>(`/api/templates/${id}/duplicate`);
    return fixTemplate(data);
  },
  async setActive(id, active, opts) {
    const { data } = await http.put<Template>(`/api/templates/${id}/active`, { active, replaceFestival: !!opts?.replaceFestival });
    return fixTemplate(data);
  },
  async uploadImage(file, fileName, onProgress) {
    const form = new FormData();
    form.append('file', file, fileName);
    const { data } = await http.post<Asset>('/api/assets', form, {
      onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0),
    });
    return fixAsset(data);
  },
  async listFestivals() {
    const { data } = await http.get<Festival[]>('/api/festivals');
    return data;
  },
  async createFestival(input) {
    const { data } = await http.post<Festival>('/api/festivals', input);
    return data;
  },
  async serverRender(id, values) {
    const { data } = await http.post<{ imageUrl: string; chatbotRequest: Record<string, unknown> }>(`/api/templates/${id}/render`, { values });
    // comes back as a data: URL, test renders aren't saved server side
    return { imageUrl: data.imageUrl, chatbotRequest: data.chatbotRequest };
  },
};

// drops the key, AuthGate picks up the event and shows sign in
export function logout() {
  setAuth(null);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export async function checkAuth(): Promise<boolean> {
  try {
    await http.get('/api/auth/check');
    return true;
  } catch (e) {
    if (e instanceof StoreError && e.status === 401) return false;
    throw e;
  }
}
