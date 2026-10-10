export function Pagination({ label, page, hasNext, disabled, onPage }: { label: string; page: number; hasNext: boolean; disabled?: boolean; onPage: (page: number) => void }) {
  return <nav aria-label={label} className="mt-4 flex items-center justify-between gap-3">
    <button type="button" className="button-secondary" disabled={disabled || page === 0} onClick={() => onPage(page - 1)}>上一页</button>
    <span className="text-sm text-muted">第 {page + 1} 页</span>
    <button type="button" className="button-secondary" disabled={disabled || !hasNext} onClick={() => onPage(page + 1)}>下一页</button>
  </nav>;
}
