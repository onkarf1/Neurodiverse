import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, json } from './api';
import { useAuth } from './auth';
import { Layout } from './components/Layout';
import { ConfirmDialog, ErrorState, LoadingState } from './components/ui';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Library from './pages/Library';
import CheckWorkspace from './pages/CheckWorkspace';
import TryActivity from './pages/TryActivity';
import History from './pages/History';

export default function App() {
  const { user, loading, error, retry } = useAuth();
  const [resetOpen, setResetOpen] = useState(false);
  const client = useQueryClient();
  const navigate = useNavigate();
  const reset = useMutation({ mutationFn: () => api('/reset', json('POST', {})), onSuccess: () => { client.clear(); setResetOpen(false); navigate('/'); toast.success('Fresh start! Your demo workspace has been restored.') }, onError: (e: Error) => toast.error(e.message) });
  useEffect(() => { const show = () => setResetOpen(true); window.addEventListener('strivetrack:reset', show); return () => window.removeEventListener('strivetrack:reset', show) }, []);
  if (loading) return <div className="auth-loading"><LoadingState rows={3} /></div>;
  if (error) return <div className="auth-loading"><ErrorState message={error} retry={retry} /></div>;
  return <><Routes><Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />{user ? <Route element={<Layout />}><Route index element={<Dashboard />} /><Route path="goals" element={<Library key="goals" kind="goals" />} /><Route path="activities" element={<Library key="activities" kind="activities" />} /><Route path="check" element={<CheckWorkspace />} /><Route path="try/:activityId" element={<TryActivity />} /><Route path="history" element={<History />} /><Route path="*" element={<Navigate to="/" replace />} /></Route> : <Route path="*" element={<Navigate to="/login" replace />} />}</Routes>{user && resetOpen && <ConfirmDialog title="Start fresh with the demo?" description="This restores all seeded goals, activities, reviews, and observations. Changes you made in this local demo will be removed." onClose={() => setResetOpen(false)} onConfirm={() => reset.mutate()} pending={reset.isPending} confirmLabel="Reset demo" />}</>;
}
