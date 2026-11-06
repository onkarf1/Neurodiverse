import { useDeferredValue, useEffect, useId, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, ArrowRight, BookOpen, CalendarDays, Check, ChevronDown, Goal as GoalIcon, Pencil, Plus, Search, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { api, date, json, query } from '../api';
import type { Activity, Goal, Paginated } from '../types';
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, LoadingState, Modal, PageHeader } from '../components/ui';
import Pagination from '../components/Pagination';

type Entity = Goal | Activity;
const isGoal = (item: Entity): item is Goal => 'skill_description' in item;
export default function Library({ kind }: { kind: 'goals' | 'activities' }) {
  const goalMode = kind === 'goals';
  const label = goalMode ? 'goal' : 'activity';
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search);
  const [status, setStatus] = useState(params.get('status') || '');
  const [sort, setSort] = useState('updated_at');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Entity | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Entity | null>(null);
  const editId = params.get('edit');
  const linked = useQuery({ queryKey: [kind, 'edit', editId], queryFn: () => api<Entity>(`/${kind}/${editId}`), enabled: !!editId });
  useEffect(() => { if (linked.data) { setEditing(linked.data); setParams(next => { next.delete('edit'); return next }, { replace: true }) } }, [linked.data, setParams]);
  const { data, isPending, error, refetch } = useQuery({ queryKey: [kind, { q: deferredSearch, status, sort, page }], queryFn: () => api<Paginated<Entity>>(`/${kind}${query({ q: deferredSearch, status, sort, order: sort === 'title' ? 'asc' : 'desc', page, page_size: 9 })}`) });
  const remove = useMutation({ mutationFn: (id: string) => api(`/${kind}/${id}`, json('DELETE')), onSuccess: () => { toast.success(`${goalMode ? 'Goal' : 'Activity'} deleted`); setDeleting(null); if (data?.items.length === 1 && page > 1) setPage(page - 1); void client.invalidateQueries() }, onError: (e: Error) => toast.error(e.message) });
  const archive = useMutation({ mutationFn: (item: Entity) => api<Entity>(`/${kind}/${item.id}`, json('PATCH', { status: item.status === 'archived' ? goalMode ? 'active' : 'draft' : 'archived' })),
    onMutate: async item => { await client.cancelQueries({ queryKey: [kind] }); const previous = client.getQueriesData<Paginated<Entity>>({ queryKey: [kind] }); client.setQueriesData<Paginated<Entity>>({ queryKey: [kind] }, old => old ? { ...old, items: old.items.map(row => row.id === item.id ? { ...row, status: item.status === 'archived' ? (goalMode ? 'active' : 'draft') : 'archived' } as Entity : row) } : old); return { previous } },
    onError: (e: Error, _item, context) => { context?.previous.forEach(([key, value]) => client.setQueryData(key, value)); toast.error(e.message) },
    onSuccess: () => toast.success('Library updated'), onSettled: () => { void client.invalidateQueries() },
  });
  return <div className="page-stack"><PageHeader eyebrow={goalMode ? 'THE PURPOSE BEHIND THE PRACTICE' : 'EVERYDAY PRACTICE, THOUGHTFULLY PREPARED'} title={goalMode ? 'Goals that guide the way' : 'Your activity library'} description={goalMode ? 'Keep approved goals and their supports together, so every activity starts with intention.' : 'A home for small tasks that build meaningful, real-world skills.'} action={<Button onClick={() => setEditing('new')} icon={<Plus size={18} />}>New {label}</Button>} />
    <div className="library-note"><span className={`icon-bubble small ${goalMode ? 'lavender' : 'peach'}`}>{goalMode ? <GoalIcon size={19} /> : <BookOpen size={19} />}</span><span>{goalMode ? 'Reference approved goals here. StriveTrack never writes or approves an IEP.' : 'Check an activity, review the evidence, and make it ready for a learner.'}</span></div>
    <div className="toolbar library-toolbar"><div className="search-input"><Search size={18} /><input aria-label={`Search ${kind}`} value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder={`Find ${goalMode ? 'a goal or skill' : 'an activity'}…`} /></div><div className="filter-controls"><label className="filter-select"><span className="sr-only">Filter by status</span><select value={status} onChange={e => { setStatus(e.target.value); setPage(1) }}><option value="">All statuses</option>{(goalMode ? ['active', 'archived'] : ['draft', 'needs_review', 'approved', 'archived']).map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select><ChevronDown size={16} /></label><label className="filter-select"><span className="sr-only">Sort results</span><select value={sort} onChange={e => { setSort(e.target.value); setPage(1) }}><option value="updated_at">Recently updated</option><option value="title">Title A–Z</option><option value="due_date">Due date</option></select><ChevronDown size={16} /></label></div></div>
    {isPending ? <LoadingState rows={6} /> : error ? <ErrorState message={error.message} retry={() => void refetch()} /> : !data?.items.length ? <EmptyState title={search || status ? 'No matches just yet' : `Your first ${label} starts here`} description={search || status ? 'Try another search or clear the status filter.' : `Add a ${label} to start building purposeful practice.`} action={<Button variant="secondary" onClick={() => { if (search || status) { setSearch(''); setStatus(''); setPage(1) } else setEditing('new') }}>{search || status ? 'Clear filters' : `Create ${label}`}</Button>} /> : <><div className="library-grid">{data.items.map((item, index) => <motion.article className="clay-card library-card" key={item.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ type: 'spring', duration: .23, bounce: .1, delay: (index % 3) * .025 }}><div className="library-card-top"><span className={`icon-bubble ${isGoal(item) ? ['lavender', 'mint', 'peach'][index % 3] : item.color}`}>{isGoal(item) ? <GoalIcon size={24} /> : <BookOpen size={24} />}</span><Badge status={item.status} /></div><span className="category-label">{item.category}</span><h2>{item.title}</h2><p className="card-description">{isGoal(item) ? item.skill_description : item.content}</p>{isGoal(item) ? <div className="supports-line"><ShieldCheck size={15} /><span>{item.accommodations.length} approved {item.accommodations.length === 1 ? 'support' : 'supports'}</span></div> : <div className="supports-line"><CalendarDays size={15} /><span>Due {date(item.due_date)}</span></div>}<div className="library-card-footer">{isGoal(item) ? <button className="text-link" onClick={() => setEditing(item)}>View goal <ArrowRight size={16} /></button> : <Link className="text-link" to={`/check?activity=${item.id}`}>{item.status === 'approved' ? 'Review & try' : 'Check alignment'} <ArrowRight size={16} /></Link>}<div className="icon-actions"><Button variant="ghost" aria-label={`Edit ${item.title}`} onClick={() => setEditing(item)}><Pencil size={16} /></Button><Button variant="ghost" aria-label={`${item.status === 'archived' ? 'Restore' : 'Archive'} ${item.title}`} disabled={archive.isPending} onClick={() => archive.mutate(item)}><Archive size={16} /></Button><Button variant="ghost" aria-label={`Delete ${item.title}`} onClick={() => setDeleting(item)}><Trash2 size={16} /></Button></div></div></motion.article>)}</div><Pagination page={page} pages={data.pages} total={data.total} onChange={setPage} /></>}
    {editing && <Editor key={editing === 'new' ? 'new' : editing.id} kind={kind} item={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} />}
    {deleting && <ConfirmDialog title={`Delete this ${label}?`} description={`“${deleting.title}” will be removed. Linked records are protected, so a ${label} with review history may need to be archived instead.`} onClose={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting.id)} pending={remove.isPending} confirmLabel={`Delete ${label}`} />}
  </div>;
}

function Editor({ kind, item, onClose }: { kind: 'goals' | 'activities'; item?: Entity; onClose: () => void }) {
  const goalMode = kind === 'goals';
  const formId = useId();
  const goal = item && isGoal(item) ? item : undefined;
  const activity = item && !isGoal(item) ? item : undefined;
  const client = useQueryClient();
  const goals = useQuery({ queryKey: ['goal-options'], queryFn: () => api<Paginated<Goal>>('/goals?page_size=100&sort=title&order=asc'), enabled: !goalMode });
  const [title, setTitle] = useState(item?.title || '');
  const [description, setDescription] = useState(goal?.skill_description || activity?.content || '');
  const [criteria, setCriteria] = useState(goal?.success_criteria || '');
  const [supports, setSupports] = useState(goal?.accommodations.join('\n') || '');
  const [category, setCategory] = useState(item?.category || '');
  const [goalId, setGoalId] = useState(activity?.goal_id || '');
  const [dueDate, setDueDate] = useState(item?.due_date || '');
  const [status, setStatus] = useState(item?.status || (goalMode ? 'active' : 'draft'));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({ mutationFn: (body: object) => api(`/${kind}${item ? `/${item.id}` : ''}`, json(item ? 'PATCH' : 'POST', body)), onSuccess: () => { toast.success(`${goalMode ? 'Goal' : 'Activity'} ${item ? 'updated' : 'created'}`); void client.invalidateQueries(); onClose() } });
  function submit(e: FormEvent) {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (title.trim().length < 3) next.title = 'Give it a clear title of at least 3 characters.';
    if (description.trim().length < 10) next.description = 'Add at least 10 characters so there is enough context.';
    if (!category.trim()) next.category = 'Add a category to keep your library organized.';
    if (!dueDate) next.due_date = 'Choose a target date.';
    if (goalMode && criteria.trim().length < 5) next.criteria = 'Include the approved success criteria.';
    if (!goalMode && !goalId) next.goal_id = 'Select the approved goal this activity practices.';
    setErrors(next);
    if (Object.keys(next).length) {
      const form = e.currentTarget;
      window.requestAnimationFrame(() => form.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    const base = { title: title.trim(), category: category.trim(), status, due_date: dueDate };
    save.mutate(goalMode ? { ...base, skill_description: description.trim(), success_criteria: criteria.trim(), accommodations: supports.split('\n').map(s => s.trim()).filter(Boolean) } : { ...base, content: description.trim(), goal_id: goalId, color: activity?.color || 'peach' });
  }
  return <Modal title={`${item ? 'Edit' : 'New'} ${goalMode ? 'approved goal' : 'activity'}`} onClose={onClose} wide><form onSubmit={submit} noValidate className="editor-form">
    <p className="muted">{goalMode ? 'Use the goal and supports from the approved plan. This reference does not change an IEP.' : 'Give your activity a goal and enough detail for a useful alignment check.'}</p>
    {Object.keys(errors).length > 0 && <p className="field-error" role="alert">Check the highlighted fields to continue.</p>}
    <div className="form-field"><label htmlFor={`${formId}-title`}>Title</label><input id={`${formId}-title`} className="clay-input" value={title} maxLength={140} onChange={e => setTitle(e.target.value)} aria-invalid={!!errors.title} aria-describedby={errors.title ? `${formId}-title-error` : undefined} autoFocus />{errors.title && <span id={`${formId}-title-error`} className="field-error">{errors.title}</span>}</div>
    {!goalMode && <div className="form-field"><label htmlFor={`${formId}-goal`}>Approved goal</label>{goals.isPending ? <span className="muted">Loading goals…</span> : goals.error ? <ErrorState message={goals.error.message} retry={() => void goals.refetch()} /> : <select id={`${formId}-goal`} className="clay-input" value={goalId} onChange={e => setGoalId(e.target.value)} aria-invalid={!!errors.goal_id} aria-describedby={errors.goal_id ? `${formId}-goal-error` : undefined}><option value="">Choose a goal</option>{goals.data?.items.map(g => <option key={g.id} value={g.id}>{g.title}{g.status === 'archived' ? ' (archived)' : ''}</option>)}</select>}{!goals.isPending && !goals.error && !goals.data?.items.length && <span className="field-error">Create an approved goal before adding an activity.</span>}{errors.goal_id && <span id={`${formId}-goal-error`} className="field-error">{errors.goal_id}</span>}</div>}
    <div className="form-field"><label htmlFor={`${formId}-description`}>{goalMode ? 'Skill description' : 'Worksheet / activity content'}</label><textarea id={`${formId}-description`} className="clay-input" rows={goalMode ? 3 : 7} maxLength={goalMode ? 5000 : 20000} value={description} onChange={e => setDescription(e.target.value)} aria-invalid={!!errors.description} aria-describedby={errors.description ? `${formId}-description-error` : undefined} />{errors.description && <span id={`${formId}-description-error`} className="field-error">{errors.description}</span>}</div>
    {goalMode && <><div className="form-field"><label htmlFor={`${formId}-criteria`}>Approved success criteria</label><textarea id={`${formId}-criteria`} className="clay-input" rows={2} value={criteria} maxLength={2500} onChange={e => setCriteria(e.target.value)} aria-invalid={!!errors.criteria} aria-describedby={errors.criteria ? `${formId}-criteria-error` : undefined} />{errors.criteria && <span id={`${formId}-criteria-error`} className="field-error">{errors.criteria}</span>}</div><div className="form-field"><label htmlFor={`${formId}-supports`}>Approved accommodations</label><span id={`${formId}-supports-hint`} className="field-hint">One support per line. These must stay in every revision.</span><textarea id={`${formId}-supports`} className="clay-input" rows={3} value={supports} maxLength={6000} onChange={e => setSupports(e.target.value)} aria-describedby={`${formId}-supports-hint`} /></div></>}
    <div className="form-grid"><div className="form-field"><label htmlFor={`${formId}-category`}>Category</label><input id={`${formId}-category`} className="clay-input" maxLength={80} value={category} onChange={e => setCategory(e.target.value)} aria-invalid={!!errors.category} aria-describedby={errors.category ? `${formId}-category-error` : undefined} />{errors.category && <span id={`${formId}-category-error`} className="field-error">{errors.category}</span>}</div><div className="form-field"><label htmlFor={`${formId}-date`}>Target date</label><input id={`${formId}-date`} className="clay-input" type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} aria-invalid={!!errors.due_date} aria-describedby={errors.due_date ? `${formId}-date-error` : undefined} />{errors.due_date && <span id={`${formId}-date-error`} className="field-error">{errors.due_date}</span>}</div></div>
    <div className="form-field"><label htmlFor={`${formId}-status`}>Status</label><select id={`${formId}-status`} className="clay-input" value={status} onChange={e => setStatus(e.target.value as Entity['status'])} aria-describedby={!goalMode ? `${formId}-status-hint` : undefined}>{(goalMode ? ['active', 'archived'] : ['draft', 'needs_review', 'archived']).concat(activity?.status === 'approved' ? ['approved'] : []).map(s => <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>)}</select>{!goalMode && <span id={`${formId}-status-hint`} className="field-hint">Approval happens in the review workspace after supports are checked.</span>}</div>
    {save.error && <p role="alert" className="field-error">{save.error.message}</p>}<div className="form-actions"><Button variant="ghost" type="button" onClick={onClose}>Cancel</Button><Button type="submit" disabled={save.isPending || (!goalMode && goals.isPending)} icon={<Check size={17} />}>{save.isPending ? 'Saving…' : `Save ${goalMode ? 'goal' : 'activity'}`}</Button></div>
  </form></Modal>;
}
