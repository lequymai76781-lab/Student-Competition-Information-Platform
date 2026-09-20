import type {
  CompetitionDetail,
  CompetitionListItem,
  CompetitionRecognition,
  PolicyCoverageSummary,
  PlatformStats,
  RecommendationResult,
  Tag,
  University,
  UniversityPolicy
} from "@/lib/types";
import universities985Seed from "../../../data/seeds/985_universities.json";

export const mockTags: Tag[] = [
  { id: 1, name: "计算机", category: "competition" },
  { id: 2, name: "新闻传播", category: "competition" },
  { id: 3, name: "创新创业", category: "competition" },
  { id: 4, name: "AIGC", category: "competition" },
  { id: 5, name: "数学建模", category: "competition" },
  { id: 6, name: "广告设计", category: "competition" },
  { id: 7, name: "体育", category: "competition" }
];

export const categoryOptions = [
  "科技创新",
  "人工智能",
  "计算机",
  "大数据",
  "数学建模",
  "电子信息",
  "机械工程",
  "商业分析",
  "创新创业",
  "市场营销",
  "新闻传播",
  "广告设计",
  "影视制作",
  "AIGC",
  "艺术设计",
  "语言文学",
  "外语",
  "体育",
  "电子竞技",
  "社会实践",
  "公益",
  "综合类",
  "其他"
];

export const mockCompetitions: CompetitionListItem[] = [
  {
    id: 1,
    name: "中国大学生计算机设计大赛",
    short_name: "计算机设计大赛",
    description: "覆盖软件应用、数字媒体、AIGC 与计算机实践的综合赛事。",
    organizer: "演示主办单位",
    category: "计算机",
    competition_level: "国家级",
    team_type: "团队赛",
    difficulty_level: "中等",
    recommended_grade: "大一,大二,大三,大四",
    status: "active",
    registration_deadline: "2026-11-05T00:00:00Z",
    current_status: "registration_open",
    tags: [mockTags[0], mockTags[1], mockTags[3]],
    is_demo: true
  },
  {
    id: 2,
    name: "全国大学生广告艺术大赛",
    short_name: "大广赛",
    description: "面向广告创意、新闻传播、视觉设计和品牌表达的实践赛事。",
    organizer: "演示主办单位",
    category: "广告设计",
    competition_level: "国家级",
    team_type: "团队赛",
    difficulty_level: "中等",
    recommended_grade: "大一,大二,大三,大四",
    status: "active",
    registration_deadline: "2026-10-06T00:00:00Z",
    current_status: "registration_open",
    tags: [mockTags[1], mockTags[3], mockTags[5]],
    is_demo: true
  },
  {
    id: 3,
    name: "挑战杯",
    short_name: "挑战杯",
    description: "侧重科技创新、社会实践与创业计划的综合赛事。",
    organizer: "演示主办单位",
    category: "科技创新",
    competition_level: "国家级",
    team_type: "团队赛",
    difficulty_level: "较高",
    recommended_grade: "大一,大二,大三,大四",
    status: "active",
    registration_deadline: "2026-10-14T00:00:00Z",
    current_status: "registration_open",
    tags: [mockTags[2]],
    is_demo: true
  },
  {
    id: 4,
    name: "全国大学生数学建模竞赛",
    short_name: "数模国赛",
    description: "强调数学建模、数据分析、论文表达和团队协作。",
    organizer: "演示主办单位",
    category: "数学建模",
    competition_level: "国家级",
    team_type: "团队赛",
    difficulty_level: "较高",
    recommended_grade: "大二,大三,大四",
    status: "active",
    registration_deadline: "2026-09-18T00:00:00Z",
    current_status: "closing_soon",
    tags: [mockTags[4]],
    is_demo: true
  }
];

export const mockCompetitionDetails: CompetitionDetail[] = mockCompetitions.map((competition) => ({
  ...competition,
  english_name: null,
  official_website: null,
  target_students: "普通高等学校本科生、研究生；具体资格以官方通知为准。",
  min_team_size: competition.team_type === "个人赛" ? 1 : 1,
  max_team_size: competition.team_type === "个人赛" ? 1 : 5,
  is_cross_major_supported: true,
  is_cross_university_supported: competition.team_type === "团队赛",
  editions: [
    {
      id: competition.id,
      year: 2026,
      edition_name: `2026${competition.name}`,
      registration_start: "2026-08-20T00:00:00Z",
      registration_deadline: competition.registration_deadline,
      competition_start: "2026-11-20T00:00:00Z",
      competition_end: "2026-12-20T00:00:00Z",
      announcement_date: "2026-08-15T00:00:00Z",
      official_url: null,
      current_status: competition.current_status ?? "unknown"
    }
  ],
  sources: [
    {
      id: competition.id,
      source_type: "official",
      source_name: "演示官方来源",
      source_url: `https://example.com/demo/competition/${competition.id}`,
      source_platform: "demo",
      is_official: true,
      is_verified: true,
      reliability_tier: 1,
      verification_status: "verified_official",
      raw_title: `${competition.name}演示来源`,
      is_demo: true
    }
  ],
  fact_sources: [],
  university_notices: [],
  official_verification_status: "已核验",
  updated_at: "2026-08-30T00:00:00Z"
}));

export const mockUniversities: University[] = [
  { id: 1, name: "武汉体育学院", short_name: "武体", province: "湖北", city: "武汉", university_type: "体育类", is_985: false, is_211: false, is_double_first_class: false, official_website: "https://www.whsu.edu.cn" },
  { id: 2, name: "武汉大学", short_name: "武大", province: "湖北", city: "武汉", university_type: "综合类", is_985: true, is_211: true, is_double_first_class: true, official_website: "https://www.whu.edu.cn" },
  { id: 3, name: "华中科技大学", short_name: "华科", province: "湖北", city: "武汉", university_type: "理工类", is_985: true, is_211: true, is_double_first_class: true, official_website: "https://www.hust.edu.cn" },
  { id: 4, name: "浙江大学", short_name: "浙大", province: "浙江", city: "杭州", university_type: "综合类", is_985: true, is_211: true, is_double_first_class: true, official_website: "https://www.zju.edu.cn" },
  { id: 5, name: "北京师范大学", short_name: "北师大", province: "北京", city: "北京", university_type: "师范类", is_985: true, is_211: true, is_double_first_class: true, official_website: "https://www.bnu.edu.cn" }
];

export const mockPolicies: UniversityPolicy[] = [
  {
    id: 1,
    university_id: 1,
    policy_name: "武汉体育学院 2026 recommendation 演示政策",
    policy_type: "recommendation",
    year: 2026,
    source_url: "https://example.com/demo/policies/1",
    content: "演示政策文本，不代表该校真实竞赛认可或加分规则。demo_data=true。",
    is_verified: false,
    is_demo: true
  },
  {
    id: 2,
    university_id: 1,
    policy_name: "武汉体育学院 2026 comprehensive_evaluation 演示政策",
    policy_type: "comprehensive_evaluation",
    year: 2026,
    source_url: "https://example.com/demo/policies/2",
    content: "演示政策文本，不代表该校真实竞赛认可或加分规则。demo_data=true。",
    is_verified: false,
    is_demo: true
  }
];

export const mockRecognitions: CompetitionRecognition[] = [
  {
    id: 1,
    university_id: 1,
    university_name: "武汉体育学院",
    competition_id: 1,
    competition_name: "中国大学生计算机设计大赛",
    policy_id: 1,
    policy_name: "武汉体育学院 2026 recommendation 演示政策",
    year: 2026,
    recognition_status: "uncertain",
    recognized_level: "演示级别",
    score: null,
    usage_type: "recommendation",
    notes: "演示数据：请以学校官方政策核验为准。",
    evidence_text: "demo_data=true",
    is_demo: true
  }
];

export const mockStats: PlatformStats = {
  competitions: 15,
  universities: 5,
  policies: 10,
  recognitions: 20,
  tags: 23,
  universities_985_total: universities985Seed.length,
  universities_985_seeded: universities985Seed.length,
  real_policy_documents: 0,
  verified_policy_documents: 0,
  college_policy_documents: 0,
  review_queue_pending: 0,
  universities_with_real_policy: 0,
  candidate_competitions: 0,
  demo_data: true
};

export const mockPolicyCoverage: PolicyCoverageSummary = {
  universities_985_total: universities985Seed.length,
  universities_985_seeded: universities985Seed.length,
  universities_with_real_policy: 0,
  real_policy_documents: 0,
  verified_policy_documents: 0,
  college_policy_documents: 0,
  parsed_college_policy_documents: 0,
  candidate_competitions: 0,
  competitions: 0,
  recognitions: 0,
  review_queue_pending: 0,
  progress: universities985Seed.map((university, index) => ({
    university_id: index + 1,
    university_name: university.name,
    short_name: university.short_name,
    province: university.province,
    city: university.city,
    official_domain: university.official_domain,
    seeded: true,
    college_count: 0,
    policy_documents_count: 0,
    verified_policy_documents_count: 0,
    parsed_policy_documents_count: 0,
    competition_count: 0,
    recognition_count: 0,
    review_pending_count: 0,
    latest_policy_year: null,
    crawl_status: "not_started"
  }))
};

export const mockRecommendations: RecommendationResult[] = [
  {
    competition_id: 1,
    competition_name: "中国大学生计算机设计大赛",
    score: 86,
    matched_factors: ["与新闻传播方向相关", "当前大二适合参加", "与AIGC技能匹配"],
    unmatched_factors: ["学校政策认可仍需官方核验"],
    recommendation_reason: "与新闻传播方向相关；当前大二适合参加；与AIGC技能匹配"
  },
  {
    competition_id: 2,
    competition_name: "全国大学生广告艺术大赛",
    score: 78,
    matched_factors: ["与广告设计和新闻传播相关", "团队赛适合跨专业协作"],
    unmatched_factors: ["政策收益需要补充学校数据"],
    recommendation_reason: "与广告设计和新闻传播相关；团队赛适合跨专业协作"
  }
];
