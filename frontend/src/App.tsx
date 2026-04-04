import type { ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { Shell } from '@/components/Shell';
import { GlobalAssistant } from '@/components/GlobalAssistant';
import { useAuth } from '@/context/AuthContext';
import { AdminPage } from '@/pages/AdminPage';
import { AuthPage } from '@/pages/AuthPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { HistoryPage } from '@/pages/HistoryPage';
import { NewsPage } from '@/pages/NewsPage';
import { PredictPage } from '@/pages/PredictPage';

function FullScreenState({ title, description }: { title: string; description: string }) {
  return (
    <div className="fullscreen-state">
      <div className="panel panel--compact panel--centered">
        <div className="spinner" />
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { status, isAuthenticated } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <FullScreenState title="Checking session" description="Validating your login against the backend." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { status, isAuthenticated, isAdmin } = useAuth();

  if (status === 'loading') {
    return <FullScreenState title="Checking permissions" description="Loading admin access." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!isAdmin) {
    return (
      <div className="page-content">
        <div className="panel panel--centered">
          <p className="eyebrow">Access denied</p>
          <h2>Admin role required</h2>
          <p>You are signed in, but this account does not have admin permissions.</p>
        </div>
      </div>
    );
  }

  return children;
}

export default function App() {
  return (
    <>
      <GlobalAssistant />
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route element={<Shell />}>
          <Route index element={<DashboardPage />} />
          <Route path="predict" element={<PredictPage />} />
          <Route
            path="history"
            element={
              <RequireAuth>
                <HistoryPage />
              </RequireAuth>
            }
          />
          <Route path="news" element={<NewsPage />} />
          <Route
            path="admin"
            element={
              <RequireAdmin>
                <AdminPage />
              </RequireAdmin>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
