export class ApiError extends Error { status: number; constructor(message: string, status: number) { super(message); this.status = status } }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('strivetrack-token');
  const response = await fetch(`${import.meta.env.VITE_API_URL || '/api'}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const fields = Array.isArray(body.errors) ? body.errors.map((item: { field: string; message: string }) => `${item.field.replaceAll('_', ' ') || 'Request'}: ${item.message.replace(/^Value error, /, '')}`).join(' ') : '';
    const detail = fields ? fields : typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((item: { msg: string }) => item.msg).join('. ') : 'Something went wrong. Please try again.';
    if (response.status === 401 && path !== '/auth/login') window.dispatchEvent(new Event('strivetrack:unauthorized'));
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const json = (method: string, body?: unknown): RequestInit => ({ method, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') search.set(key, String(value)) });
  return `?${search}`;
}
export const date = (value: string) => value ? new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'America/Phoenix' }).format(new Date(value.length === 10 ? `${value}T12:00:00-07:00` : value)) : 'No date';
export const normalizeSupport = (text: string) => text.split(/\s+/).filter(Boolean).join(' ').toLocaleLowerCase();
