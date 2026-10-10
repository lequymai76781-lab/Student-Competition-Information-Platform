export function formatDate(value?: string | null): string {
  if (!value) {
    return "暂未核实";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai"
  }).format(new Date(value));
}

export function daysUntil(value?: string | null): string {
  if (!value) {
    return "暂未核实";
  }
  const diff = new Date(value).getTime() - Date.now();
  const days = Math.ceil(diff / (1000 * 60 * 60 * 24));
  if (diff < 0) {
    return "已截止";
  }
  if (days === 0) {
    return "今天截止";
  }
  return `${days}天后截止`;
}

export function statusLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    active: "正常收录",
    registration_open: "报名中",
    registration_upcoming: "即将开始报名",
    submission_open: "作品提交中",
    upcoming: "即将开始",
    closing_soon: "即将截止",
    closed: "已截止",
    registration_closed: "报名已截止",
    ongoing: "进行中",
    finished: "已结束",
    ended: "已截止",
    result_announced: "结果公布",
    unknown: "暂未核实"
  };
  return labels[status ?? "unknown"] ?? status ?? "暂未核实";
}

export function verificationLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    verified_official: "官方来源已核验",
    verified_manual: "人工核验通过",
    authority_confirmed: "权威目录收录",
    association_confirmed: "高教学会/全国学会目录收录",
    official_site_confirmed: "官方赛事网站已确认",
    school_confirmed: "高校正式收录",
    pending_verification: "信息核验中",
    verified_multi_source: "多来源交叉核实",
    secondary_source_only: "仅有二级来源",
    unverified: "暂未核实",
    conflicting: "来源存在冲突",
    suspected: "对象性质待复核",
    duplicate: "已判定重复",
    non_competition: "非正式竞赛"
  };
  return labels[status ?? "unverified"] ?? "暂未核实";
}

export function verificationTone(status?: string | null): string {
  const tones: Record<string, string> = {
    verified_official: "border-emerald-200 bg-emerald-50 text-emerald-700",
    verified_manual: "border-blue-200 bg-blue-50 text-blue-700",
    authority_confirmed: "border-blue-200 bg-blue-50 text-blue-700",
    association_confirmed: "border-blue-200 bg-blue-50 text-blue-700",
    official_site_confirmed: "border-blue-200 bg-blue-50 text-blue-700",
    school_confirmed: "border-slate-300 bg-slate-100 text-slate-700",
    pending_verification: "border-amber-200 bg-amber-50 text-amber-800",
    unverified: "border-slate-200 bg-slate-50 text-muted",
    suspected: "border-amber-200 bg-amber-50 text-amber-800",
    conflicting: "border-red-200 bg-red-50 text-red-700",
    secondary_source_only: "border-slate-200 bg-slate-50 text-muted",
    duplicate: "border-slate-200 bg-slate-50 text-muted",
    non_competition: "border-slate-200 bg-slate-50 text-muted"
  };
  return tones[status ?? "unverified"] ?? "border-slate-200 bg-slate-50 text-muted";
}

export function freshnessLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    fresh: "近期已核验",
    due_for_check: "建议复查",
    stale: "信息已过期",
    archived: "历史届次",
    unknown: "核验时间未知"
  };
  return labels[status ?? "unknown"] ?? "核验时间未知";
}

export function freshnessDate(value?: string | null): string {
  if (!value) return "核验时间未知";
  return `最近核验：${formatDate(value)}`;
}
