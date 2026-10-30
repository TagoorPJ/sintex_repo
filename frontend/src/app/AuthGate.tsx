import { KeyRound } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { FestiveBackdrop } from '@/components/FestiveBackdrop';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button } from '@/components/ui/Button';
import { FieldLabel, TextInput } from '@/components/ui/controls';
import { Notice } from '@/components/ui/feedback';
import { AUTH_EVENT, checkAuth, setAuth } from '@/features/templates/store/httpStore';

// admin key login. swap for SSO if this ends up behind it
export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'ok' | 'needed' | 'offline'>('checking');
  const [key, setKey] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    checkAuth()
      .then((ok) => setState(ok ? 'ok' : 'needed'))
      .catch(() => setState('offline'));
    const onAuth = () => {
      setKey('');
      setState('needed');
    };
    window.addEventListener(AUTH_EVENT, onAuth);
    return () => window.removeEventListener(AUTH_EVENT, onAuth);
  }, []);

  if (state === 'ok') return <>{children}</>;
  if (state === 'checking') return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    setAuth({ key: key.trim(), user: '' });
    try {
      if (await checkAuth()) setState('ok');
      else setError('That key was not accepted.');
    } catch {
      setError("Can't reach the server.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-full bg-bg lg:grid-cols-[1.05fr_1fr]">
      {/* brand panel, becomes a banner on small screens */}
      <aside className="relative flex min-h-56 flex-col justify-between overflow-hidden p-6 text-white sm:p-10 lg:min-h-full lg:p-14">
        <FestiveBackdrop className="absolute inset-0 size-full" />
        {/* optional photo - put one at public/brand/login-bg.jpg and it gets picked up */}
        <img
          src={`${import.meta.env.BASE_URL}brand/login-bg.jpg`}
          alt=""
          className="absolute inset-0 size-full object-cover opacity-0 transition-opacity duration-500"
          onLoad={(e) => e.currentTarget.classList.replace('opacity-0', 'opacity-100')}
          onError={(e) => e.currentTarget.remove()}
        />
        <div className="absolute inset-0 bg-linear-to-t from-[#4a070b]/35 via-transparent to-transparent" aria-hidden />
        <img
          src={`${import.meta.env.BASE_URL}brand/sintex-logo.png`}
          alt="Sintex — Sabse safe, hamesha!"
          className="relative w-40 brightness-0 invert drop-shadow-[0_2px_6px_rgb(0_0_0/0.25)] sm:w-52"
        />
        <div className="relative mt-8 hidden max-w-md lg:block">
          <h2 className="text-4xl font-semibold leading-tight tracking-tight">Festive greetings for every Sintex partner</h2>
          <p className="mt-4 text-base text-white/85">
            Design the card once. On WhatsApp, the chatbot fills in each partner's name, enterprise and number and sends their own greeting.
          </p>
        </div>
        <p className="relative mt-6 hidden text-sm text-white/70 lg:block">Sintex · A Welspun company</p>
      </aside>

      {/* sign in */}
      <main className="relative flex items-center justify-center p-6 sm:p-10">
        <div className="absolute right-4 top-4">
          <ThemeToggle size="md" />
        </div>
        <form
          className="w-full max-w-sm"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <img
            src={`${import.meta.env.BASE_URL}brand/sintex-by-welspun.png`}
            alt="Sintex by Welspun"
            className="mb-8 h-14 w-auto rounded-lg dark:bg-white dark:p-2 dark:box-content"
          />
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Greeting Template Studio</h1>
          <p className="mt-1.5 text-sm text-fg-2">Sign in with the admin key to create and manage festive greeting cards.</p>
          {state === 'offline' && (
            <Notice level="error" className="mt-5">
              Can't reach the greeting service. Start the backend (see README) and reload this page.
            </Notice>
          )}
          <div className="mt-6 space-y-4">
            <div>
              <FieldLabel htmlFor="admin-key">Admin key</FieldLabel>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-3" aria-hidden />
                <TextInput
                  id="admin-key"
                  type="password"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  autoComplete="current-password"
                  autoFocus
                  required
                  className="h-10 pl-9 text-sm"
                />
              </div>
            </div>
            {error && <p className="text-[12px] text-danger-text">{error}</p>}
            <Button type="submit" variant="primary" size="md" className="h-10 w-full" loading={busy} disabled={!key.trim()}>
              Sign in
            </Button>
          </div>
          <p className="mt-8 text-[12px] text-fg-3">Templates you save here are used by the Sintex WhatsApp chatbot.</p>
        </form>
      </main>
    </div>
  );
}