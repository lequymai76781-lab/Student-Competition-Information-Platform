import { LayoutGrid, List, TableProperties } from "lucide-react";

export function ViewToolbar({ resultCount }: { resultCount: number }) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-muted">
        找到 <strong className="font-semibold text-ink">{resultCount}</strong> 个竞赛条目
      </p>
      <div className="flex min-h-11 items-center rounded-md border border-line bg-paper p-1">
        <button className="flex h-9 items-center gap-2 rounded px-3 text-sm font-semibold text-accent shadow-sm bg-white" type="button">
          <LayoutGrid aria-hidden className="h-4 w-4" />
          Card
        </button>
        <button className="flex h-9 items-center gap-2 rounded px-3 text-sm font-medium text-muted" type="button">
          <List aria-hidden className="h-4 w-4" />
          List
        </button>
        <button className="hidden h-9 items-center gap-2 rounded px-3 text-sm font-medium text-muted sm:flex" type="button">
          <TableProperties aria-hidden className="h-4 w-4" />
          Table
        </button>
      </div>
    </div>
  );
}
