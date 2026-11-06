import { useEffect, useId, useRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AlertCircle, Inbox, LoaderCircle, X } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: ReactNode;
};

export function Button({ variant = 'primary', icon, children, className = '', type = 'button', ...props }: ButtonProps) {
  return <button type={type} className={`clay-button button-${variant} ${className}`} {...props}>{icon}{children}</button>;
}

const labels: Record<string, string> = {
  needs_review: 'Needs review', active: 'Active', archived: 'Archived', approved: 'Approved',
  draft: 'Draft', blocked: 'Needs support', rejected: 'Rejected', superseded: 'Superseded', aligned: 'Aligned',
  mismatch: 'Alignment gap', unsure: 'More detail needed', planning: 'Planning',
};

export function Badge({ status, color, children }: { status?: string; color?: string; children?: ReactNode }) {
  return <span className={`badge badge-${color || status || 'neutral'}`}>{children || (status && (labels[status] || status.replaceAll('_', ' ')))}</span>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="page-header-action">{action}</div>}</header>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state clay-card"><span className="icon-orb orb-lavender"><Inbox size={27} aria-hidden="true" /></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function LoadingState({ rows = 3 }: { rows?: number }) {
  return <div className="loading-state" role="status" aria-live="polite"><span className="sr-only">Loading your workspace…</span>{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton clay-card"><span /><span /><span /></div>)}</div>;
}

export function ErrorState({ message = 'We couldn’t load this part of your workspace. Please try again.', retry }: { message?: string; retry?: () => void }) {
  return <div className="empty-state clay-card" role="alert"><span className="icon-orb orb-peach"><AlertCircle size={27} aria-hidden="true" /></span><h3>A small hiccup</h3><p>{message}</p>{retry && <Button variant="secondary" onClick={retry}>Try again</Button>}</div>;
}

export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const titleId = useId();
  const reducedMotion = useReducedMotion();
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const timer = window.setTimeout(() => {
      const first = panel.current?.querySelector<HTMLElement>('input:not([disabled]),select:not([disabled]),textarea:not([disabled])') || panel.current?.querySelector<HTMLElement>('button:not([disabled]),[tabindex="0"]');
      first?.focus();
    }, 30);
    function keydown(event: KeyboardEvent) {
      if (event.key === 'Escape') close.current();
      if (event.key !== 'Tab') return;
      const nodes = panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex="0"]');
      if (!nodes?.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener('keydown', keydown);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener('keydown', keydown);
      document.body.style.overflow = oldOverflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><motion.div initial={reducedMotion ? false : { opacity: 0, y: 18, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.18 }} className={`modal-panel clay-card ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={panel}><div className="modal-header"><h2 id={titleId}>{title}</h2><button className="icon-button" type="button" aria-label="Close dialog" onClick={onClose}><X size={21} /></button></div>{children}</motion.div></div>;
}

export function ConfirmDialog({ title, description, onConfirm, onClose, pending = false, tone = 'danger', confirmLabel = 'Confirm', cancelLabel = 'Cancel' }: { title: string; description: string; onConfirm: () => void; onClose: () => void; pending?: boolean; tone?: 'danger' | 'primary'; confirmLabel?: string; cancelLabel?: string }) {
  return <Modal title={title} onClose={onClose}><p className="confirm-description">{description}</p><div className="form-actions"><Button variant="secondary" onClick={onClose} disabled={pending}>{cancelLabel}</Button><Button variant={tone} onClick={onConfirm} disabled={pending} icon={pending ? <LoaderCircle className="spin" size={17} /> : undefined}>{pending ? 'Working…' : confirmLabel}</Button></div></Modal>;
}

export function StatCard({ label, value, detail, icon, color = 'mint' }: { label: string; value: number | string; detail?: string; icon: ReactNode; color?: string }) {
  return <div className="stat-card clay-card"><div className="stat-top"><span className={`icon-orb orb-${color}`}>{icon}</span>{detail && <span className="stat-detail">{detail}</span>}</div><strong className="stat-value">{value}</strong><span className="stat-label">{label}</span></div>;
}
