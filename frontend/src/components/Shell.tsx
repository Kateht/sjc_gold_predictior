import { NavLink, Outlet, Link } from 'react-router-dom';

import { APP_NAME } from '@/lib/config';
import { useAuth } from '@/context/AuthContext';

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/predict', label: 'Predict' },
  { to: '/history', label: 'History', auth: true },
  { to: '/news', label: 'News' },
  { to: '/admin', label: 'Admin', admin: true },
];

export function Shell() {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();

  const visibleItems = navItems.filter((item) => {
    if (item.admin) {
      return isAdmin;
    }
    if (item.auth) {
      return isAuthenticated;
    }
    return true;
  });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">G</div>
          <div>
            <p className="eyebrow">Live gold intelligence</p>
            <h1>{APP_NAME}</h1>
          </div>
        </div>

        <div className="sidebar-intro">
          <span className="sidebar-section__label">Workspace</span>
          <p>Monitor market data, run forecasts, inspect history, and switch into admin controls without losing context.</p>
        </div>

        <div className="sidebar-nav__header">
          <span className="sidebar-section__label">Navigation</span>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {visibleItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-card">
          <p className="sidebar-card__label">Session</p>
          {isAuthenticated && user ? (
            <>
              <strong>{user.name}</strong>
              <span>{user.email}</span>
              <span className={`role-badge role-badge--${user.role}`}>{user.role}</span>
              <button type="button" className="button button--ghost button--full" onClick={() => void logout()}>
                Log out
              </button>
            </>
          ) : (
            <>
              <strong>Guest access</strong>
              <span>Sign in to view history and admin controls.</span>
              <Link className="button button--primary button--full" to="/login">
                Log in
              </Link>
            </>
          )}
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Gold market control room</p>
            <h2>Prediction, overview, and operations in one place</h2>
          </div>
          <div className="topbar__actions">
            <span className="status-pill status-pill--live">Backend ready</span>
            {isAuthenticated && user ? <span className="status-pill">{user.role}</span> : null}
          </div>
        </header>

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
