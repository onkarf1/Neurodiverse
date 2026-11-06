import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './ui';
export default function Pagination({ page, pages, total, onChange }: { page: number; pages: number; total: number; onChange: (page: number) => void }) {
  return <div className="pagination"><span className="muted">{total} {total === 1 ? 'result' : 'results'}{pages > 1 ? ` · Page ${page} of ${pages}` : ''}</span><div><Button variant="ghost" disabled={page <= 1} aria-label="Previous page" onClick={() => onChange(page - 1)}><ChevronLeft size={18} /></Button><Button variant="ghost" disabled={page >= pages || pages === 0} aria-label="Next page" onClick={() => onChange(page + 1)}><ChevronRight size={18} /></Button></div></div>;
}
