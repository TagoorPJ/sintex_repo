import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark' | 'system';

const KEY = 'greeting-theme';
const media = window.matchMedia('(prefers-color-scheme: dark)');

function readMode(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  } catch {
    return 'system';
  }
}

function apply(mode: ThemeMode) {
  const dark = mode === 'dark' || (mode === 'system' && media.matches);
  document.documentElement.classList.toggle('dark', dark);
}

export const useTheme = create<{ mode: ThemeMode; setMode: (m: ThemeMode) => void }>((set) => ({
  mode: readMode(),
  setMode: (mode) => {
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* no storage, choice only lasts for this page */
    }
    apply(mode);
    set({ mode });
  },
}));

// also follows OS changes while mode is "system"
export function initTheme() {
  apply(useTheme.getState().mode);
  media.addEventListener('change', () => apply(useTheme.getState().mode));
}
