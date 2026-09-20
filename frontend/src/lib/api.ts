import type {
  ApiResponse,
  CompetitionDiscoveryCoverageSummary,
  CompetitionDetail,
  CompetitionListItem,
  CompetitionRecognition,
  PlatformStats,
  PolicyCoverageSummary,
  RecommendationRequest,
  RecommendationResult,
  Tag,
  University,
  UniversityDetail,
  UniversityPolicy
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

const emptyStats: PlatformStats = {
  competitions: 0,
  universities: 0,
  policies: 0,
  recognitions: 0,
  tags: 0,
  universities_985_total: 39,
  universities_985_seeded: 0,
  universities_with_real_policy: 0,
  real_policy_documents: 0,
  verified_policy_documents: 0,
  college_policy_documents: 0,
  candidate_competitions: 0,
  review_queue_pending: 0,
  editions: 0,
  verified_editions: 0,
  registration_open: 0,
  submission_open: 0,
  tagged_competitions: 0,
  github_seed_sources: 0,
  competition_leads: 0,
  github_discovery_leads: 0,
  university_official_leads: 0,
  third_party_platform_leads: 0,
  wechat_leads: 0,
  social_leads: 0,
  universities_crawled: 0,
  competition_discovery_scanned_985: 0,
  competition_discovery_completed_985: 0,
  competition_discovery_partial_985: 0,
  competition_discovery_failed_985: 0,
  competition_discovery_blocked_985: 0,
  universities_with_competition_leads: 0,
  universities_with_competitions: 0,
  universities_with_2026_editions: 0,
  university_competition_notices: 0,
  college_competition_notices: 0,
  internal_deadline_count: 0,
  official_registration_deadline_count: 0,
  registration_notice_count: 0,
  internal_selection_count: 0,
  submission_notice_count: 0,
  non_action_notice_count: 0,
  competitions_with_description: 0,
  competitions_with_organizer: 0,
  competitions_with_official_website: 0,
  competitions_with_founded_year: 0,
  field_fact_sources: 0,
  detail_ready_competitions: 0,
  competitions_with_history_timeline: 0,
  competitions_with_participation_requirements: 0,
  competitions_with_competition_process: 0,
  competitions_with_submission_requirements: 0,
  competitions_with_award_settings: 0,
  editions_with_fee_information: 0,
  policy_raw_items: 0,
  verified_official_competitions: 0,
  verified_multi_source_competitions: 0,
  secondary_source_only_competitions: 0,
  source_distribution: {},
  demo_data: false
};

const emptyPolicyCoverage: PolicyCoverageSummary = {
  universities_985_total: 39,
  universities_985_seeded: 0,
  universities_with_real_policy: 0,
  real_policy_documents: 0,
  verified_policy_documents: 0,
  college_policy_documents: 0,
  parsed_college_policy_documents: 0,
  candidate_competitions: 0,
  competitions: 0,
  recognitions: 0,
  review_queue_pending: 0,
  progress: []
};

const emptyCompetitionDiscoveryCoverage: CompetitionDiscoveryCoverageSummary = {
  universities_985_total: 39,
  universities_985_seeded: 0,
  scanned_985_count: 0,
  completed_985_count: 0,
  completed_with_gaps_985_count: 0,
  partial_985_count: 0,
  failed_985_count: 0,
  blocked_985_count: 0,
  universities_211_non_985_total: 73,
  universities_211_non_985_seeded: 0,
  scanned_211_non_985_count: 0,
  completed_211_non_985_count: 0,
  completed_with_gaps_211_non_985_count: 0,
  partial_211_non_985_count: 0,
  failed_211_non_985_count: 0,
  blocked_211_non_985_count: 0,
  universities_with_leads: 0,
  universities_with_matched_competitions: 0,
  universities_with_2026_editions: 0,
  competition_leads: 0,
  matched_competitions: 0,
  new_competitions: 0,
  new_editions: 0,
  official_sources: 0,
  university_notice_count: 0,
  college_notice_count: 0,
  current_registration_count: 0,
  edition_2026_count: 0,
  wechat_leads: 0,
  university_relations: 0,
  internal_deadlines: 0,
  discovery_methods: {
    sitemap: 0,
    department_feed: 0,
    site_search: 0,
    external_search: 0,
    wechat: 0,
    reverse_match: 0,
    navigation: 0,
    status_by_scope: {}
  },
  source_distribution: {},
  progress_985: [],
  progress_211_non_985: [],
  progress: []
};

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      cache: "no-store"
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as ApiResponse<T>;
    return payload.success ? payload.data : null;
  } catch {
    return null;
  }
}

function withQuery(path: string, params?: Record<string, string | number | undefined | null>): string {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      query.set(key, `${value}`);
    }
  });
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

export async function getStats(): Promise<PlatformStats> {
  return (await request<PlatformStats>("/stats")) ?? emptyStats;
}

export async function getPolicyCoverage(): Promise<PolicyCoverageSummary> {
  return (await request<PolicyCoverageSummary>("/v0.2/universities/985-progress")) ?? emptyPolicyCoverage;
}

export async function getCompetitionDiscoveryCoverage(): Promise<CompetitionDiscoveryCoverageSummary> {
  return (
    (await request<CompetitionDiscoveryCoverageSummary>("/v0.8/competitions/discovery/coverage")) ??
    emptyCompetitionDiscoveryCoverage
  );
}

export async function getTags(): Promise<Tag[]> {
  return (await request<Tag[]>("/tags")) ?? [];
}

export async function getCompetitions(params?: Record<string, string | number | undefined | null>): Promise<CompetitionListItem[]> {
  return (await request<CompetitionListItem[]>(withQuery("/competitions", params))) ?? [];
}

export async function getCompetition(
  id: string | number,
  params?: Record<string, string | number | undefined | null>
): Promise<CompetitionDetail | null> {
  return (await request<CompetitionDetail>(withQuery(`/competitions/${id}`, params))) ?? null;
}

export async function getCompetitionRecognition(id: string | number): Promise<CompetitionRecognition[]> {
  return (await request<CompetitionRecognition[]>(`/competition/${id}/university-recognition`)) ?? [];
}

export async function getCompetitionUpdates(id: string | number): Promise<unknown[]> {
  return (await request<unknown[]>(`/competitions/${id}/updates`)) ?? [];
}

export async function getUniversities(params?: Record<string, string | number | undefined | null>): Promise<University[]> {
  return (await request<University[]>(withQuery("/universities", params))) ?? [];
}

export async function getUniversity(id: string | number): Promise<UniversityDetail | null> {
  return (await request<UniversityDetail>(`/universities/${id}`)) ?? null;
}

export async function getUniversityPolicies(id: string | number): Promise<UniversityPolicy[]> {
  return (await request<UniversityPolicy[]>(`/universities/${id}/policies`)) ?? [];
}

export async function getUniversityCompetitionPolicies(id: string | number): Promise<CompetitionRecognition[]> {
  return (await request<CompetitionRecognition[]>(`/universities/${id}/competition-policies`)) ?? [];
}

export async function createRecommendations(payload: RecommendationRequest): Promise<RecommendationResult[]> {
  return (
    (await request<RecommendationResult[]>("/recommendations", {
      method: "POST",
      body: JSON.stringify(payload)
    })) ?? []
  );
}
