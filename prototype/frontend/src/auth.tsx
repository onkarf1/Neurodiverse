import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from './api';
import type { User } from './types';

interface AuthContextValue { user: User | null; loading: boolean; error: string; retry: () => void; login: (token: string, user: User) => void; logout: () => void }
const AuthContext = createContext<AuthContextValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const logout = useCallback(() => { localStorage.removeItem('strivetrack-token'); setUser(null); setError(''); client.clear() }, [client]);
  const restore = useCallback(() => {
    if (!localStorage.getItem('strivetrack-token')) { setLoading(false); return }
    setLoading(true); setError('');
    api<User>('/auth/me').then(setUser).catch((e: Error) => { if (e instanceof ApiError && e.status === 401) logout(); else setError('We could not reach your local backend. Start it and retry.') }).finally(() => setLoading(false));
  }, [logout]);
  useEffect(() => { restore(); window.addEventListener('strivetrack:unauthorized', logout); return () => window.removeEventListener('strivetrack:unauthorized', logout) }, [restore, logout]);
  const login = (token: string, nextUser: User) => { client.clear(); localStorage.setItem('strivetrack-token', token); setUser(nextUser); setError('') };
  return <AuthContext.Provider value={{ user, loading, error, retry: restore, login, logout }}>{children}</AuthContext.Provider>;
}
export function useAuth() { const auth = useContext(AuthContext); if (!auth) throw new Error('AuthProvider is required'); return auth }
