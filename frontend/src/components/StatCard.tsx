import type { LucideIcon } from "lucide-react";

type StatCardProps = {
  label: string;
  value: string | number;
  helper?: string;
  icon: LucideIcon;
};

export function StatCard({ label, value, helper, icon: Icon }: StatCardProps) {
  return (
    <div className="rounded-lg bg-surface p-4">
      <div className="flex items-start justify-between gap-3 border-l-2 border-accent/30 pl-3">
        <div>
          <p className="text-3xl font-semibold text-ink">{value}</p>
          <p className="mt-1 text-sm font-medium text-muted">{label}</p>
          {helper ? <p className="mt-1 text-xs text-quiet">{helper}</p> : null}
        </div>
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-white text-accent">
          <Icon aria-hidden className="h-4 w-4" />
        </span>
      </div>
    </div>
  );
}
