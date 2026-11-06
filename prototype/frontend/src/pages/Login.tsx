import { useState } from 'react';
import type { FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Check, Layers3, Leaf, LoaderCircle, ShieldCheck, Sparkles, Target } from 'lucide-react';
import { api } from '../api';
import { useAuth } from '../auth';
import type { User } from '../types';
import { Button, ErrorState } from '../components/ui';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const users = useQuery({ queryKey: ['demo-users'], queryFn: () => api<User[]>('/demo-users') });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('strivetrack-demo');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!email.trim()) { setError('Choose a demo teacher or enter their email to continue.'); return; }
    setPending(true);
    try {
      const result = await api<{ token: string; user: User }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
      login(result.token, result.user);
      navigate('/');
    } catch (err) { setError(err instanceof Error ? err.message : 'We couldn’t sign you in. Please try again.'); }
    finally { setPending(false); }
  }
  return <div className="login-page"><div className="login-story"><a className="brand" href="/"><span className="brand-mark"><Layers3 size={29} /></span><span>Strive<span className="brand-fit">Track</span></span></a><div className="login-story-inner"><span className="eyebrow"><Sparkles size={15} /> A LITTLE CLARITY. A LOT OF POSSIBILITY.</span><h1>Small steps.<br /><em>Meaningful</em><br />progress.</h1><p>A thoughtful workspace to make every activity fit the goal — while keeping the supports that help learners thrive.</p><div className="login-art" aria-hidden="true"><motion.div className="login-target" animate={{ y: [0, -8, 0], rotate: [-4, -1, -4] }} transition={{ repeat: Infinity, duration: 5, ease: 'easeInOut' }}><Target size={107} strokeWidth={1.5} /><span className="target-spark"><Sparkles size={26} /></span></motion.div><div className="login-art-note note-one"><span className="icon-orb orb-mint"><Check size={23} /></span><span>Every support.<br /><strong>Always included.</strong></span></div><div className="login-art-note note-two"><span className="icon-orb orb-peach"><Leaf size={24} /></span><span>More confidence.<br /><strong>More possibility.</strong></span></div><span className="art-dot dot-one" /><span className="art-dot dot-two" /></div><p className="login-story-footer"><ShieldCheck size={17} /> Teacher-led. Evidence-backed. Learner-centered.</p></div></div><div className="login-form-side"><div className="login-form-wrap"><span className="badge badge-mint"><span className="workspace-dot" /> LOCAL DEMO</span><h2>Your next good<br />teaching day starts here.</h2><p className="muted">Explore StriveTrack with a seeded demo account.</p>{users.isPending ? <div className="demo-users-loading" role="status">Loading demo teachers…</div> : users.isError ? <ErrorState message="Start the local backend to load demo accounts." retry={() => { void users.refetch(); }} /> : users.data?.length ? <div className="demo-user-list" aria-label="Choose a demo account">{users.data.map(user => <button key={user.id} className={`demo-user ${email === user.email ? 'selected' : ''}`} type="button" onClick={() => { setEmail(user.email); setError(''); }}><span className={`avatar avatar-${user.color || 'lavender'}`}>{user.initials}</span><span><strong>{user.name}</strong><small>{user.role === 'admin' ? 'Administrator' : 'Teacher'} · {user.email}</small></span><span className="demo-user-check">{email === user.email && <Check size={16} />}</span></button>)}</div> : <p role="status">No demo accounts are available. Reset the backend seed data.</p>}<form onSubmit={submit} className="login-form"><label className="form-field">Email address<input className="clay-input" name="email" type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} placeholder="Choose a demo account above" required aria-describedby={error ? 'login-error' : undefined} /></label><label className="form-field">Demo password<input className="clay-input" name="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><p className="demo-password">All demo accounts use <code>strivetrack-demo</code></p>{error && <p className="field-error" id="login-error" role="alert">{error}</p>}<Button type="submit" disabled={pending || users.isPending || users.isError} icon={pending ? <LoaderCircle size={19} className="spin" /> : undefined}>{pending ? 'Opening your workspace…' : 'Step into your workspace'}{!pending && <ArrowRight size={18} />}</Button></form><div className="login-disclaimer"><ShieldCheck size={19} /><p><strong>A safe space to explore.</strong><br />Synthetic data only. Simulated sign-in. Optional AI suggestions see only goal and activity text, never learner records.</p></div></div><p className="login-bottom">A little more aligned. A little more possible.</p></div></div>;
}
