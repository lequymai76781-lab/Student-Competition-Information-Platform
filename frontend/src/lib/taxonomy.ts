const toneByKeyword: Array<{ keywords: string[]; className: string }> = [
  {
    keywords: ["计算机", "人工智能", "AI", "AIGC", "大数据"],
    className: "border-blue-200 bg-blue-50 text-blue-700"
  },
  {
    keywords: ["数学建模"],
    className: "border-violet-200 bg-violet-50 text-violet-700"
  },
  {
    keywords: ["创新创业", "市场营销"],
    className: "border-orange-200 bg-orange-50 text-orange-700"
  },
  {
    keywords: ["新闻传播", "影视制作"],
    className: "border-pink-200 bg-pink-50 text-pink-700"
  },
  {
    keywords: ["广告设计", "艺术设计", "设计"],
    className: "border-yellow-200 bg-yellow-50 text-yellow-700"
  },
  {
    keywords: ["体育", "电子竞技"],
    className: "border-emerald-200 bg-emerald-50 text-emerald-700"
  },
  {
    keywords: ["商业分析", "金融", "商科"],
    className: "border-cyan-200 bg-cyan-50 text-cyan-700"
  },
  {
    keywords: ["科研", "科技创新", "机械工程", "电子信息"],
    className: "border-slate-200 bg-slate-50 text-slate-700"
  }
];

export function getTagTone(name?: string | null): string {
  if (!name) {
    return "border-line bg-paper text-muted";
  }
  return toneByKeyword.find((tone) => tone.keywords.some((keyword) => name.includes(keyword)))?.className ?? "border-line bg-paper text-muted";
}

export function policyTypeLabel(type?: string | null): string {
  const labels: Record<string, string> = {
    recommendation: "保研 / 推免",
    comprehensive_evaluation: "综测",
    scholarship: "奖学金",
    competition_reward: "竞赛奖励",
    innovation_credit: "创新创业学分",
    graduation: "毕业要求",
    other: "其他"
  };
  return labels[type ?? "other"] ?? type ?? "其他";
}

export function recognitionStatusLabel(status?: string | null): string {
  const labels: Record<string, string> = {
    recognized: "已认可",
    expired: "历史认可",
    not_recognized: "未认可",
    uncertain: "需核验",
    unknown: "未知"
  };
  return labels[status ?? "unknown"] ?? status ?? "未知";
}

export function sourceTypeLabel(type?: string | null): string {
  const labels: Record<string, string> = {
    official: "赛事官网",
    university: "高校官网",
    government: "政府 / 教育主管部门",
    competition_platform: "竞赛平台",
    wechat: "微信公众号",
    xiaohongshu: "小红书",
    weibo: "微博",
    zhihu: "知乎",
    bilibili: "B站",
    github: "GitHub",
    manual: "人工录入",
    other: "其他来源"
  };
  return labels[type ?? "other"] ?? type ?? "其他来源";
}
