import { useEffect, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';

export function AuthPage() {
  const { status, isAuthenticated, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const fromPath = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? '/';

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate(fromPath, { replace: true });
    }
  }, [isAuthenticated, navigate, fromPath]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(name, email, password);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setLoading(false);
    }
  }

  if (status === 'loading') {
    return (
      <div className="auth-shell">
        <div className="panel panel--compact panel--centered">
          <div className="spinner" />
          <h2>Checking session</h2>
          <p>Loading your account state.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <section className="auth-panel">
        <div className="auth-copy panel">
          <p className="eyebrow">SJC gold intelligence</p>
          <h1>Sign in, track predictions, and keep the market in one control room.</h1>
          <p>
            The frontend is wired to the FastAPI backend for overview, prediction, history, news, and admin workflows.
          </p>
          <div className="chip-row">
            <span className="chip">JWT auth</span>
            <span className="chip">Prediction charts</span>
            <span className="chip">Admin tools</span>
          </div>
          <div className="metric-grid metric-grid--compact">
            <div className="metric-card">
              <span className="metric-card__label">Access</span>
              <strong className="metric-card__value">Secure</strong>
              <span className="metric-card__meta">Token-based session flow</span>
            </div>
            <div className="metric-card">
              <span className="metric-card__label">Focus</span>
              <strong className="metric-card__value">Gold</strong>
              <span className="metric-card__meta">Domestic and world views</span>
            </div>
          </div>
        </div>

        <form className="auth-form panel" onSubmit={handleSubmit}>
          <div className="tabs">
            <button type="button" className={`tab ${mode === 'login' ? 'is-active' : ''}`} onClick={() => setMode('login')}>
              Log in
            </button>
            <button type="button" className={`tab ${mode === 'register' ? 'is-active' : ''}`} onClick={() => setMode('register')}>
              Register
            </button>
          </div>

          <div className="stack">
            {mode === 'register' ? (
              <label className="field">
                <span>Name</span>
                <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" required />
              </label>
            ) : null}

            <label className="field">
              <span>Email</span>
              <input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" required />
            </label>

            <label className="field">
              <span>Password</span>
              <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" required />
            </label>
          </div>

          {error ? <div className="error-state">{error}</div> : null}

          <button type="submit" className="button button--primary button--full" disabled={loading}>
            {loading ? 'Working...' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>

          <p className="auth-form__footnote">
            Back to <Link to="/">dashboard</Link>. Need admin access? Use the seeded admin account from backend.
          </p>
        </form>
      </section>
    </div>
  );
}
