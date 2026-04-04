import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import {
  clearAuthSession,
  fetchCurrentUser,
  getCurrentSession,
  loginUser,
  logoutUser,
  registerUser,
  saveAuthSession,
} from '@/lib/api';
import type { AuthSession, UserRead } from '@/types';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated';

interface AuthContextValue {
  session: AuthSession | null;
  user: UserRead | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function syncStoredSession(): Promise<AuthSession | null> {
  const session = getCurrentSession();
  if (!session) {
    return null;
  }

  try {
    const user = await fetchCurrentUser();
    const nextSession = { ...session, user };
    saveAuthSession(nextSession);
    return nextSession;
  } catch {
    clearAuthSession();
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initialSession = getCurrentSession();
  const [session, setSession] = useState<AuthSession | null>(initialSession);
  const [status, setStatus] = useState<AuthStatus>(initialSession ? 'loading' : 'anonymous');

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      const storedSession = getCurrentSession();
      if (!storedSession) {
        if (active) {
          setStatus('anonymous');
          setSession(null);
        }
        return;
      }

      const nextSession = await syncStoredSession();
      if (!active) {
        return;
      }

      if (nextSession) {
        setSession(nextSession);
        setStatus('authenticated');
      } else {
        setSession(null);
        setStatus('anonymous');
      }
    }

    void bootstrap();
    return () => {
      active = false;
    };
  }, []);

  async function login(email: string, password: string) {
    const nextSession = await loginUser(email, password);
    saveAuthSession(nextSession);
    setSession(nextSession);
    setStatus('authenticated');
  }

  async function register(name: string, email: string, password: string) {
    const nextSession = await registerUser(name, email, password);
    saveAuthSession(nextSession);
    setSession(nextSession);
    setStatus('authenticated');
  }

  async function logout() {
    const storedSession = getCurrentSession();
    try {
      if (storedSession?.refreshToken) {
        await logoutUser(storedSession.refreshToken);
      }
    } catch {
      // Clear local state even if the revoke call fails.
    } finally {
      clearAuthSession();
      setSession(null);
      setStatus('anonymous');
    }
  }

  async function refreshSession() {
    const nextSession = await syncStoredSession();
    if (nextSession) {
      setSession(nextSession);
      setStatus('authenticated');
      return;
    }
    clearAuthSession();
    setSession(null);
    setStatus('anonymous');
  }

  const value: AuthContextValue = {
    session,
    user: session?.user ?? null,
    status,
    isAuthenticated: status === 'authenticated' && Boolean(session),
    isAdmin: session?.user.role === 'admin',
    login,
    register,
    logout,
    refreshSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
