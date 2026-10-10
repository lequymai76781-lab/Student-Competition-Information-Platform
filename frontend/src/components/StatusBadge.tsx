import { CheckCircle2, Clock3, Megaphone, Rocket, ShieldQuestion, type LucideIcon } from "lucide-react";

import { statusLabel } from "@/lib/format";

const defaultStatusMeta = {
  icon: ShieldQuestion,
  tone: "border-slate-200 bg-slate-50 text-muted"
};

const statusMeta: Record<string, { icon: LucideIcon; tone: string }> = {
  报名中: {
    icon: CheckCircle2,
    tone: "border-emerald-200 bg-emerald-50 text-emerald-700"
  },
  即将开始: {
    icon: Rocket,
    tone: "border-blue-200 bg-blue-50 text-blue-700"
  },
  即将截止: {
    icon: Clock3,
    tone: "border-orange-200 bg-orange-50 text-orange-700"
  },
  已截止: {
    icon: Clock3,
    tone: "border-slate-200 bg-slate-50 text-slate-600"
  },
  报名已截止: {
    icon: Clock3,
    tone: "border-slate-200 bg-slate-50 text-slate-600"
  },
  进行中: {
    icon: Rocket,
    tone: "border-blue-200 bg-blue-50 text-blue-700"
  },
  已结束: {
    icon: Clock3,
    tone: "border-slate-200 bg-slate-50 text-slate-600"
  },
  结果公布: {
    icon: Megaphone,
    tone: "border-violet-200 bg-violet-50 text-violet-700"
  }
};

export function StatusBadge({ status, closingSoon }: { status?: string | null; closingSoon?: boolean }) {
  const label = status === "registration_open" && closingSoon ? "即将截止" : statusLabel(status);
  const { icon: Icon, tone } = statusMeta[label] ?? defaultStatusMeta;

  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold ${tone}`}>
      <Icon aria-hidden className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}
