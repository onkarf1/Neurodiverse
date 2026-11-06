import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChevronDown, ClipboardCheck, History, LayoutDashboard, Layers3, LogOut, Moon, RotateCcw, ShieldCheck, Sparkles, Sun, Target } from 'lucide-react';
import { useAuth } from '../auth';

const navigation = [
  { to: '/', label: 'Overview', Icon: LayoutDashboard },
  { to: '/goals', label: 'Goal library', short: 'Goals', Icon: Target },
  { to: '/activities', label: 'Activities', Icon: BookOpen },
  { to: '/check', label: 'Alignment check', short: 'Check', Icon: ClipboardCheck },
  { to: '/history', label: 'Activity history', short: 'History', Icon: History },
];

export function Layout() {
  const { user, logout } = useAuth();
  const [dark, setDark] = useState(() => localStorage.getItem('strivetrack:theme') === 'dark');
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('strivetrack:theme', dark ? 'dark' : 'light');
  }, [dark]);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar" aria-label="Main navigation">
      <Link to="/" className="brand" aria-label="StriveTrack home"><span className="brand-mark"><Layers3 size={27} strokeWidth={2.3} /></span><span>Strive<span className="brand-fit">Track</span><small>SMALL STEPS. REAL POSSIBILITIES.</small></span></Link>
      <div className="workspace-switcher clay-pressed"><span className="school-avatar">CG</span><div><strong>Cedar Grove</strong><small>Demo school</small></div><ChevronDown size={15} aria-hidden="true" /></div>
      <p className="nav-label">YOUR WORKSPACE</p>
      <nav className="sidebar-nav">{navigation.map(({ to, label, Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={21} strokeWidth={1.8} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="mini-spark"><Sparkles size={20} /></span><h3>Every support stays.</h3><p>Thoughtful activities.<br />Teacher-led decisions.</p><Link to="/check">Let’s find the fit <ArrowUpRight size={15} /></Link></div><button className="sidebar-reset" onClick={() => window.dispatchEvent(new Event('strivetrack:reset'))}><RotateCcw size={15} /> Reset demo workspace</button><div className="sidebar-user"><span className={`avatar avatar-${user?.color || 'lavender'}`}>{user?.initials || 'ST'}</span><div><strong>{user?.name}</strong><small>{user?.role === 'admin' ? 'School administrator' : 'Special education teacher'}</small></div><button className="icon-button" aria-label="Sign out" onClick={logout}><LogOut size={17} /></button></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><Link to="/" className="mobile-brand"><span className="brand-mark"><Layers3 size={21} /></span><strong>StriveTrack</strong></Link><div className="breadcrumb"><span className="workspace-dot" /> Cedar Grove <span className="breadcrumb-divider">/</span> Teaching workspace</div><div className="topbar-actions"><span className="demo-pill"><ShieldCheck size={14} /> Demo workspace</span><button className="icon-button theme-toggle" aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'} onClick={() => setDark(value => !value)}>{dark ? <Sun size={19} /> : <Moon size={19} />}</button><span className={`avatar topbar-avatar avatar-${user?.color || 'lavender'}`} title={user?.name}>{user?.initials || 'ST'}</span><MobileAccountMenu /></div></header><main id="main-content" className="main-content" tabIndex={-1}><Outlet /></main><footer className="workspace-footer"><span>Made for meaningful learning.</span><span><span className="workspace-dot" /> Synthetic data · Local demo</span></footer></div>
    <nav className="mobile-nav" aria-label="Main navigation">{navigation.map(({ to, label, short, Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => isActive ? 'active' : ''}><Icon size={20} /><span>{short || label}</span></NavLink>)}</nav>
  </div>;
}

function MobileAccountMenu() {
  const { user, logout } = useAuth();
  const details = useRef<HTMLDetailsElement>(null);
  function close(restoreFocus = false) {
    if (!details.current) return;
    details.current.open = false;
    if (restoreFocus) details.current.querySelector('summary')?.focus();
  }
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (details.current?.open && !details.current.contains(event.target as Node)) close();
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape' && details.current?.open) { event.preventDefault(); close(true); }
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, []);
  return <details ref={details} className="mobile-account-menu" onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) close(); }}>
    <summary aria-label="Account and demo controls"><span className={`avatar avatar-${user?.color || 'lavender'}`}>{user?.initials || 'ST'}</span></summary>
    <div className="mobile-account-panel clay-card"><div className="mobile-account-identity"><strong>{user?.name}</strong><small>{user?.email}</small></div><button type="button" onClick={() => { close(true); window.dispatchEvent(new Event('strivetrack:reset')); }}><RotateCcw size={16} /> Reset demo workspace</button><button type="button" onClick={() => { close(); logout(); }}><LogOut size={16} /> Sign out</button></div>
  </details>;
}
