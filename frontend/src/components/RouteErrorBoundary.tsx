import { AlertCircle, ArrowLeft, RefreshCw } from 'lucide-react';
import { isRouteErrorResponse, Link, useRouteError } from 'react-router';
import { Button } from '@/components/ui/Button';

export function RouteErrorBoundary() {
  const error = useRouteError();

  let title = 'Something went wrong';
  let message = 'An unexpected error occurred while loading this page.';
  let details: string | null = null;

  if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`;
    message = typeof error.data === 'string' ? error.data : error.data?.message || 'The requested page could not be loaded.';
  } else if (error instanceof Error) {
    message = error.message;
    details = error.stack || null;
  } else if (typeof error === 'string') {
    message = error;
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-workspace p-6 text-center">
      <div className="mx-auto max-w-md rounded-2xl border border-line bg-surface p-8 shadow-dialog">
        <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-danger-subtle text-danger-text">
          <AlertCircle className="size-7" aria-hidden />
        </div>
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        <p className="mt-2 text-sm text-fg-2">{message}</p>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button
            variant="primary"
            icon={<RefreshCw className="size-4" />}
            onClick={() => window.location.reload()}
          >
            Reload page
          </Button>
          <Link
            to="/templates"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-4 text-sm font-medium text-fg hover:bg-hover"
          >
            <ArrowLeft className="size-4" aria-hidden /> Back to templates
          </Link>
        </div>

        {details && (
          <details className="mt-6 text-left">
            <summary className="cursor-pointer text-[12px] font-medium text-fg-3 hover:text-fg">
              Technical details
            </summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-lg bg-sunken p-3 text-[11px] leading-relaxed text-fg-2 font-mono">
              {details}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}
