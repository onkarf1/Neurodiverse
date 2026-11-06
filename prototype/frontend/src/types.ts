export interface User { id: string; name: string; email: string; role: string; initials: string; color: string }
export interface RecordBase { id: string; created_at: string; updated_at: string }
export interface Goal extends RecordBase { title: string; skill_description: string; success_criteria: string; accommodations: string[]; category: string; status: 'active' | 'archived'; due_date: string; created_by: string }
export interface Activity extends RecordBase { goal_id: string; title: string; content: string; category: string; status: 'draft' | 'needs_review' | 'approved' | 'archived'; due_date: string; color: string; created_by: string }
export type AssistMode = 'ai-assisted' | 'deterministic-demo';
export interface Revision extends RecordBase { activity_id: string; goal_id: string; content: string; status: 'draft' | 'blocked' | 'approved' | 'rejected' | 'superseded'; version: number; blocked_reason: string | null; superseded_by?: number; accommodations: string[]; created_by: string; mode?: AssistMode; ai_model?: string | null; ai_rationale?: string | null; ai_note?: string | null }
export interface Observation extends RecordBase { activity_id: string; note: string; context: string; created_by: string }
export interface Finding { type: string; explanation: string; evidence: string; confidence: number; source?: 'ai' | 'rules' }
export interface DemandRow { skill: string; goal_targets: boolean; activity: 'learner_does' | 'done_for_learner' | 'not_required'; note: string; source: 'ai' | 'rules' }
export interface Check { id: string; activity_id: string; goal_id: string; result: 'aligned' | 'mismatch' | 'unsure'; summary: string; findings: Finding[]; demand_map?: DemandRow[]; created_at: string; mode?: AssistMode; ai_model?: string | null; ai_note?: string | null; stale?: boolean; stale_reasons?: ('goal' | 'activity')[] }
export type Prompting = 'independent' | 'one_prompt' | 'several_prompts' | 'modeled';
export interface Session extends RecordBase { activity_id: string; version: number; learner_label: string; ordered_steps: string[]; reasoning: string; prompting: Prompting; supports_used: string[]; recorded_by: string }
export interface AiStatus { enabled: boolean; model: string | null }
export interface Audit { id: string; actor: string; action: string; target: string; target_id: string; version: number | null; created_at: string; detail: string }
export interface Paginated<T> { items: T[]; total: number; page: number; page_size: number; pages: number }
export interface DashboardData { stats: { active_goals: number; activities: number; needs_review: number; approved: number; accommodations_kept: number }; weekly: { label: string; checked: number; approved: number }[]; recent_activities: Activity[]; recent_audit: Audit[]; user: User }
export interface TryData { activity: Activity; revision: Revision; goal: Goal; steps: string[] }
