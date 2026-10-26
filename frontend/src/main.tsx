import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'motion/react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router';
import { Toaster } from 'sonner';
import { AuthGate } from './app/AuthGate';
import { initTheme } from './app/theme';
import { TooltipProvider } from './components/ui/Tooltip';
import { preloadDefaultFonts } from './features/templates/model/fonts';
import { TemplatesPage } from './features/templates/list/TemplatesPage';
import './styles.css';

void preloadDefaultFonts();

initTheme();

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

export function getStudioBase(): string {
  if (typeof window !== 'undefined' && (window as any).__ENV__?.STUDIO_BASE) {
    return (window as any).__ENV__.STUDIO_BASE.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined') {
    const p = window.location.pathname;
    const idx = p.indexOf('/studio');
    if (idx !== -1) {
      return p.slice(0, idx + '/studio'.length);
    }
  }
  return import.meta.env.BASE_URL.replace(/\/$/, '') || '/';
}

const router = createBrowserRouter(
  [
    { path: '/', element: <Navigate to="/templates" replace /> },
    { path: '/templates', element: <TemplatesPage /> },
    {
      path: '/templates/:id',
      // editor is the heavy bit, keep it out of the dashboard bundle
      lazy: async () => ({ Component: (await import('./features/templates/editor/EditorPage')).EditorPage }),
    },
    { path: '*', element: <Navigate to="/templates" replace /> },
  ],
  { basename: getStudioBase() },
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <TooltipProvider delay={400}>
          <AuthGate>
            <RouterProvider router={router} />
          </AuthGate>
          <Toaster position="bottom-center" richColors closeButton toastOptions={{ className: 'font-sans' }} />
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
);
