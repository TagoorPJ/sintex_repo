/**
 * Multi-environment URL resolver for Sintex Greeting Template Studio.
 *
 * Automatically detects the runtime environment:
 * - Localhost / Dev:  http://localhost:8000/studio/        -> apiBase: "",                 studioBase: "/studio"
 * - UAT:              https://api.wel-wise.com/sintex_agent_uat/studio/ -> apiBase: "/sintex_agent_uat", studioBase: "/sintex_agent_uat/studio"
 * - Prod:             https://api.wel-wise.com/sintex_agent/studio/     -> apiBase: "/sintex_agent",     studioBase: "/sintex_agent/studio"
 *
 * Can also be explicitly overridden at runtime via window.__ENV__ = { API_URL: "...", STUDIO_BASE: "..." }
 * or at build time via VITE_API_URL.
 */

declare global {
  interface Window {
    __ENV__?: {
      API_URL?: string;
      STUDIO_BASE?: string;
    };
  }
}

export function getApiBase(): string {
  // 1. Explicit runtime override
  if (typeof window !== 'undefined' && window.__ENV__?.API_URL) {
    return window.__ENV__.API_URL.replace(/\/$/, '');
  }
  // 2. Build-time Vite env var
  const envUrl = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '');
  if (envUrl) return envUrl;

  // 3. Dynamic auto-detection from current URL path
  if (typeof window !== 'undefined') {
    const p = window.location.pathname;
    const idx = p.indexOf('/studio');
    if (idx > 0) {
      return p.slice(0, idx);
    }
  }
  return '';
}

export function getStudioBase(): string {
  // 1. Explicit runtime override
  if (typeof window !== 'undefined' && window.__ENV__?.STUDIO_BASE) {
    return window.__ENV__.STUDIO_BASE.replace(/\/$/, '');
  }
  // 2. Dynamic auto-detection from current URL path
  if (typeof window !== 'undefined') {
    const p = window.location.pathname;
    const idx = p.indexOf('/studio');
    if (idx !== -1) {
      return p.slice(0, idx + '/studio'.length);
    }
  }
  return (import.meta.env.BASE_URL || '/studio').replace(/\/$/, '');
}

export function studioAssetUrl(path: string): string {
  const base = getStudioBase().replace(/\/$/, '');
  const cleanPath = path.replace(/^\//, '');
  return `${base}/${cleanPath}`;
}
