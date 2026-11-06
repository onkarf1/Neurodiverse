import { useEffect, useId, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowLeft, ArrowUp, BookOpenText, Check, ClipboardList, Hourglass, MessageSquareText, NotebookPen, Pause, Pencil, Play, Plus, RotateCcw, ShieldCheck, Trash2, Type, Volume2 } from 'lucide-react';
import { toast } from 'sonner';
import { api, date, json, query } from '../api';
import type { Observation, Paginated, Prompting, Session, TryData } from '../types';
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, LoadingState, Modal, PageHeader } from '../components/ui';

const promptingLabels: Record<Prompting, string> = { independent: 'Independent', one_prompt: 'One prompt', several_prompts: 'Several prompts', modeled: 'Teacher modeled' };

export default function TryActivity() {
  const { activityId = '' } = useParams();
  const data = useQuery({ queryKey: ['try', activityId], queryFn: () => api<TryData>(`/try/${activityId}`), retry: false });
  if (data.isPending) return <LoadingState rows={4} />;
  if (data.error || !data.data) return <div className="page-stack"><PageHeader title="Let’s get this activity ready" description="Approve the current revision and all its supports before recording a practice session." /><ErrorState message={data.error?.message} retry={() => void data.refetch()} /><Link to={`/check?activity=${activityId}`} className="text-link"><ArrowLeft size={17} /> Back to the review</Link></div>;
  return <TryWorkspace key={data.data.revision.id} data={data.data} />;
}

function TryWorkspace({ data }: { data: TryData }) {
  const client = useQueryClient();
  const formId = useId();
  const [steps, setSteps] = useState(data.steps);
  const [learner, setLearner] = useState('');
  const [reasoning, setReasoning] = useState('');
  const [prompting, setPrompting] = useState<Prompting>('independent');
  const [supportsUsed, setSupportsUsed] = useState<string[]>([]);
  const [large, setLarge] = useState(() => localStorage.getItem('strivetrack-large-text') === '1');
  const [readable, setReadable] = useState(() => localStorage.getItem('strivetrack-readable') === '1');
  const [saved, setSaved] = useState<Session | null>(null);
  useEffect(() => { localStorage.setItem('strivetrack-large-text', large ? '1' : '0'); localStorage.setItem('strivetrack-readable', readable ? '1' : '0') }, [large, readable]);
  const timeSupport = data.goal.accommodations.find(support => /time|pause|wait/i.test(support));
  const [error, setError] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const submit = useMutation({
    mutationFn: () => api<{ session: Session }>(`/try/${data.activity.id}/submit`, json('POST', { ordered_steps: steps, learner_label: learner.trim(), reasoning: reasoning.trim(), prompting, supports_used: supportsUsed })),
    onSuccess: result => { setSaved(result.session); toast.success('Practice session saved'); void client.invalidateQueries({ queryKey: ['sessions'] }); void client.invalidateQueries({ queryKey: ['audit'] }) },
    onError: (e: Error) => setError(e.message),
  });
  useEffect(() => () => { window.speechSynthesis?.cancel() }, []);
  function move(index: number, direction: number) {
    const next = [...steps]; const destination = index + direction;
    [next[index], next[destination]] = [next[destination], next[index]];
    setSteps(next); setAnnouncement(`Moved “${steps[index]}” to position ${destination + 1}.`);
  }
  function read() {
    const speech = window.speechSynthesis;
    const voice = speech?.getVoices().find(item => item.localService && item.lang.startsWith('en'));
    if (!speech || !voice) { toast.info('A local English voice is not available on this device. Your browser’s accessibility tools can read the activity.'); return }
    speech.cancel(); const utterance = new SpeechSynthesisUtterance(`${data.activity.title}. Choose the order you would use. ${steps.join('. ')}`); utterance.voice = voice; utterance.rate = .85; speech.speak(utterance);
  }
  function toggleSupport(support: string) { setSupportsUsed(current => current.includes(support) ? current.filter(item => item !== support) : [...current, support]) }
  function save(e: FormEvent) { e.preventDefault(); if (!learner.trim()) { setError('Add a learner code, such as initials or “Learner A”.'); return } setError(''); submit.mutate() }
  function startAnother() { setSaved(null); setSteps(data.steps); setReasoning(''); setPrompting('independent'); setSupportsUsed([]) }
  return <div className={`page-stack learner-page ${large ? 'large-text' : ''} ${readable ? 'readable-text' : ''}`}><Link to={`/check?activity=${data.activity.id}`} className="text-link"><ArrowLeft size={16} /> Back to the review</Link><PageHeader eyebrow="PRACTICE SESSION RECORD" title={data.activity.title} description="Show the task cards to your learner. Arrange them in the order they choose, then record how they explained it." action={<Badge status="approved">Teacher approved · v{data.revision.version}</Badge>} />
    <div className="learner-tools"><Button variant="secondary" onClick={() => setLarge(!large)} aria-pressed={large} icon={<Type size={18} />}>{large ? 'Regular text' : 'Larger cards'}</Button><Button variant="secondary" onClick={() => setReadable(!readable)} aria-pressed={readable} icon={<BookOpenText size={18} />}>{readable ? 'Standard spacing' : 'Easier reading'}</Button><Button variant="secondary" onClick={read} icon={<Volume2 size={18} />}>Read cards aloud</Button></div>
    {!saved && <ThinkingTimer support={timeSupport} onStart={() => { if (timeSupport) setSupportsUsed(current => current.includes(timeSupport) ? current : [...current, timeSupport]) }} />}
    <div className="try-grid"><section className="clay-card plan-card"><div className="section-heading"><div><div className="eyebrow">THE LEARNER’S PLAN</div><h2>{saved ? 'Session saved' : 'Order the learner chose'}</h2></div><span className="icon-bubble lavender"><ClipboardList size={25} /></span></div>
      {saved ? <div className="practice-success" role="status"><span className="icon-bubble mint"><Check size={28} /></span><h3>Saved for {saved.learner_label}.</h3><p>{promptingLabels[saved.prompting]}{saved.supports_used.length ? ` · Supports used: ${saved.supports_used.join(', ')}` : ''}. StriveTrack records the session and does not score it.</p><ol>{saved.ordered_steps.map(step => <li key={step}>{step}</li>)}</ol>{saved.reasoning && <blockquote className="session-reasoning">“{saved.reasoning}”</blockquote>}<Button variant="secondary" onClick={startAnother}>Record another session</Button></div>
      : <form onSubmit={save} noValidate className="session-form"><p className="muted">Use the arrow buttons to match the learner’s order. Every card stays in the plan.</p><ol className="step-cards">{steps.map((step, index) => <li key={step} className="clay-card step-card"><span className="step-number">{index + 1}</span><span className="step-text">{step}</span><div className="step-movers"><button type="button" className="icon-button" disabled={index === 0} aria-label={`Move step ${index + 1} up`} onClick={() => move(index, -1)}><ArrowUp size={19} /></button><button type="button" className="icon-button" disabled={index === steps.length - 1} aria-label={`Move step ${index + 1} down`} onClick={() => move(index, 1)}><ArrowDown size={19} /></button></div></li>)}</ol><span className="sr-only" role="status" aria-live="polite">{announcement}</span>
        <div className="form-grid"><div className="form-field"><label htmlFor={`${formId}-learner`}>Learner code</label><input id={`${formId}-learner`} className="clay-input" value={learner} maxLength={40} onChange={e => setLearner(e.target.value)} aria-describedby={`${formId}-learner-hint`} aria-invalid={!!error && !learner.trim()} /><span id={`${formId}-learner-hint`} className="field-hint">Initials or a code, never a full name.</span></div><div className="form-field"><label htmlFor={`${formId}-prompting`}>Prompting needed</label><select id={`${formId}-prompting`} className="clay-input" value={prompting} onChange={e => setPrompting(e.target.value as Prompting)}>{Object.entries(promptingLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div>
        <div className="form-field"><label htmlFor={`${formId}-reasoning`}>How did the learner explain their order?</label><textarea id={`${formId}-reasoning`} className="clay-input" rows={3} maxLength={2000} value={reasoning} onChange={e => setReasoning(e.target.value)} placeholder="For example: “I get the supplies first so I don’t have to walk back.”" /></div>
        {data.goal.accommodations.length > 0 && <fieldset className="form-field supports-used"><legend>Supports used in this session</legend>{data.goal.accommodations.map(support => <label key={support} className="support-check"><input type="checkbox" checked={supportsUsed.includes(support)} onChange={() => toggleSupport(support)} /> {support}</label>)}</fieldset>}
        {error && <p role="alert" className="field-error">{error}</p>}<Button type="submit" disabled={submit.isPending} icon={<NotebookPen size={18} />}>{submit.isPending ? 'Saving the session…' : 'Save practice session'}</Button></form>}
    </section><aside className="clay-card learner-supports"><span className="icon-bubble mint"><ShieldCheck size={25} /></span><h2>Approved supports</h2><p>Provide each of these during the session. Taking time is part of making a plan.</p>{data.goal.accommodations.map(support => <div className="support-item" key={support}><Check size={16} /><span>{support}</span></div>)}{!data.goal.accommodations.length && <p className="muted">No accommodations are recorded for this goal.</p>}<details><summary>Read the approved activity</summary><p className="worksheet-content">{data.revision.content}</p></details></aside></div>
    <SessionHistory activityId={data.activity.id} />
    <TeacherObservations activityId={data.activity.id} />
  </div>;
}

function ThinkingTimer({ support, onStart }: { support?: string; onStart: () => void }) {
  const [total, setTotal] = useState(60);
  const [left, setLeft] = useState(60);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setLeft(current => { if (current <= 1) { setRunning(false); return 0 } return current - 1 }), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  function choose(seconds: number) { setTotal(seconds); setLeft(seconds); setRunning(false) }
  function toggle() { if (left === 0) setLeft(total); if (!running) onStart(); setRunning(!running) }
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
  return <section className="clay-card thinking-timer" aria-labelledby="thinking-timer-title"><span className="icon-bubble lemon"><Hourglass size={22} /></span><div className="thinking-timer-body"><h2 id="thinking-timer-title">Thinking time</h2><p className="muted">{support ? `Approved support: ${support}. Starting the timer marks it as used.` : 'A calm, visible countdown while the learner plans. No rush, no score.'}</p><div className="timer-bar" aria-hidden="true"><span style={{ width: `${(left / total) * 100}%` }} /></div></div><div className="thinking-timer-controls"><div className="timer-lengths" role="group" aria-label="Timer length">{[60, 120, 180].map(seconds => <button type="button" key={seconds} className={`subtle-chip ${total === seconds ? 'selected' : ''}`} aria-pressed={total === seconds} onClick={() => choose(seconds)}>{seconds / 60} min</button>)}</div><strong className="timer-clock" aria-hidden="true">{clock}</strong><span className="sr-only" role="status">{left === 0 ? 'Thinking time is over. The learner can share their plan when ready.' : ''}</span><Button variant="secondary" onClick={toggle} icon={running ? <Pause size={17} /> : <Play size={17} />}>{running ? 'Pause' : left === 0 ? 'Restart' : left < total ? 'Resume' : 'Start'}</Button><Button variant="ghost" aria-label="Reset timer" onClick={() => choose(total)}><RotateCcw size={16} /></Button></div></section>;
}

function SessionHistory({ activityId }: { activityId: string }) {
  const sessions = useQuery({ queryKey: ['sessions', activityId], queryFn: () => api<Paginated<Session>>(`/sessions${query({ activity_id: activityId, page_size: 20, sort: 'created_at', order: 'desc' })}`) });
  return <section className="clay-card observations-section"><div className="section-heading"><div><div className="eyebrow">PRACTICE SESSIONS</div><h2>Recorded sessions</h2><p>Each learner’s chosen order and reasoning, next to your notes.</p></div></div>{sessions.isPending ? <LoadingState rows={2} /> : sessions.error ? <ErrorState message={sessions.error.message} retry={() => void sessions.refetch()} /> : !sessions.data?.items.length ? <EmptyState title="No sessions yet" description="Save a practice session above to see it here." /> : <div className="observation-list">{sessions.data.items.map(item => <article className="observation-item" key={item.id}><span className="icon-bubble small lavender"><ClipboardList size={19} /></span><div><p><strong>{item.learner_label}</strong> · {promptingLabels[item.prompting]} · v{item.version}</p><p>{item.ordered_steps.map((step, index) => `${index + 1}. ${step}`).join('   ')}</p>{item.reasoning && <span className="observation-context">Reasoning: “{item.reasoning}”</span>}{item.supports_used.length > 0 && <span className="observation-context">Supports used: {item.supports_used.join(', ')}</span>}<span className="observation-date">Recorded by {item.recorded_by} · {date(item.created_at)}</span></div></article>)}</div>}</section>;
}

export function TeacherObservations({ activityId }: { activityId: string }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState<Observation | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Observation | null>(null);
  const observations = useQuery({ queryKey: ['observations', activityId], queryFn: () => api<Paginated<Observation>>(`/observations${query({ activity_id: activityId, page_size: 100, sort: 'created_at', order: 'desc' })}`) });
  const remove = useMutation({ mutationFn: () => api(`/observations/${deleting!.id}`, json('DELETE')), onSuccess: () => { toast.success('Observation deleted'); setDeleting(null); void client.invalidateQueries() }, onError: (e: Error) => toast.error(e.message) });
  return <section className="clay-card observations-section"><div className="section-heading"><div><div className="eyebrow">TEACHER NOTES · SEPARATE FROM ALIGNMENT CHECKS</div><h2>What did you notice?</h2><p>Capture what happened during practice, in your own words.</p></div><Button variant="secondary" onClick={() => setEditing('new')} icon={<Plus size={17} />}>Add observation</Button></div>{observations.isPending ? <LoadingState rows={2} /> : observations.error ? <ErrorState message={observations.error.message} retry={() => void observations.refetch()} /> : !observations.data?.items.length ? <EmptyState title="Space for your perspective" description="Add a teacher observation after practice. StriveTrack does not infer progress or mastery." /> : <div className="observation-list">{observations.data.items.map(item => <article className="observation-item" key={item.id}><span className="icon-bubble small lemon"><MessageSquareText size={19} /></span><div><p>{item.note}</p>{item.context && <span className="observation-context">{item.context}</span>}<span className="observation-date">Teacher observation · {date(item.created_at)}</span></div><div className="icon-actions"><Button variant="ghost" aria-label="Edit observation" onClick={() => setEditing(item)}><Pencil size={16} /></Button><Button variant="ghost" aria-label="Delete observation" onClick={() => setDeleting(item)}><Trash2 size={16} /></Button></div></article>)}</div>}{editing && <ObservationForm key={editing === 'new' ? 'new' : editing.id} activityId={activityId} item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}{deleting && <ConfirmDialog title="Delete this observation?" description="This teacher note will be removed. The approved activity and practice history will stay." onClose={() => setDeleting(null)} onConfirm={() => remove.mutate()} pending={remove.isPending} confirmLabel="Delete observation" />}</section>;
}

function ObservationForm({ activityId, item, onClose }: { activityId: string; item?: Observation; onClose: () => void }) {
  const client = useQueryClient();
  const formId = useId();
  const [note, setNote] = useState(item?.note || '');
  const [context, setContext] = useState(item?.context || '');
  const [error, setError] = useState('');
  const save = useMutation({ mutationFn: () => api(`/observations${item ? `/${item.id}` : ''}`, json(item ? 'PATCH' : 'POST', { ...(!item ? { activity_id: activityId } : {}), note: note.trim(), context: context.trim() })), onSuccess: () => { toast.success('Teacher observation saved'); void client.invalidateQueries(); onClose() }, onError: (e: Error) => setError(e.message) });
  function submit(e: FormEvent) { e.preventDefault(); if (note.trim().length < 3) { setError('Write an observation of at least 3 characters.'); return } setError(''); save.mutate() }
  return <Modal title="Teacher observation" onClose={onClose}><form onSubmit={submit} className="editor-form" noValidate><p className="muted">Record what you observed, without learner names or identifying details. These notes stay separate from the alignment check result.</p><div className="form-field"><label htmlFor={`${formId}-note`}>Observation</label><textarea id={`${formId}-note`} className="clay-input" rows={4} value={note} maxLength={5000} onChange={e => setNote(e.target.value)} aria-invalid={!!error} aria-describedby={error ? `${formId}-error` : undefined} autoFocus /></div><div className="form-field"><label htmlFor={`${formId}-context`}>Context</label><input id={`${formId}-context`} className="clay-input" value={context} maxLength={1000} onChange={e => setContext(e.target.value)} aria-describedby={`${formId}-context-hint`} /><span id={`${formId}-context-hint`} className="field-hint">Optional: setting, materials, or supports used.</span></div>{error && <p id={`${formId}-error`} role="alert" className="field-error">{error}</p>}<div className="form-actions"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save observation'}</Button></div></form></Modal>;
}
