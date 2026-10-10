import type { CompetitionUpdateEvent } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001/api";

export type AdminCorrection = { id: number; field_review_id?: number | null; competition_name?: string | null; competition_edition_id?: number | null; correction_type: string; description: string; source_url?: string | null; status: string; editions: Array<{ id: number; name: string }> };
export type AdminLead = { id: number; title: string; classification?: string | null; source_url: string };
export type AdminCandidateFact = { id: number; field_name: string; candidate_value: unknown; confidence?: number | null; source_url: string };
export type AdminFeedback = { id: number; category: string; content: string; url?: string | null; status: string };

export type V09Profile = {
  user_id: number;
  email: string;
  university_id?: number | null;
  university_name?: string | null;
  college_id?: number | null;
  college_name?: string | null;
  major_id?: number | null;
  major_name?: string | null;
  grade?: string | null;
  graduation_year?: number | null;
  interest_tags?: string[];
  skills?: string[];
  preferred_team_type?: string | null;
  weekly_available_hours?: number | null;
  accept_cross_major?: boolean;
  accept_cross_university?: boolean;
};

export type V09Reason = { type: string; text: string };

export type V09Item = {
  competition_id: number;
  name: string;
  short_name?: string | null;
  category?: string | null;
  tags: { id: number; name: string; category?: string | null }[];
  current_status?: string | null;
  effective_deadline?: string | null;
  effective_deadline_label?: string | null;
  official_deadline?: string | null;
  university_deadline?: string | null;
  college_deadline?: string | null;
  reasons: V09Reason[];
  relation?: { notice_title?: string | null; notice_url?: string | null; notice_type?: string | null; college_name?: string | null } | null;
  school_notice?: boolean;
  college_notice?: boolean;
  favorite?: boolean;
  user_status?: string | null;
  open?: boolean;
};

export type V09Overview = {
  profile_complete: boolean;
  profile?: V09Profile;
  now_available: V09Item[];
  direction_related: V09Item[];
  school_notices: V09Item[];
  college_notices: V09Item[];
  school_directory: V09Item[];
  college_directory: V09Item[];
  upcoming_deadline: V09Item[];
  favorites: V09Item[];
  status_views: Record<string, V09Item[]>;
  counts: Record<string, number>;
};

export type SessionUser = {
  user: V09Profile;
  onboarding_complete: boolean;
};

export type AuthSession = SessionUser & { token: string };

function token(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("v09_token");
}

export function setToken(value: string | null): void {
  if (typeof window === "undefined") return;
  if (value) window.localStorage.setItem("v09_token", value);
  else window.localStorage.removeItem("v09_token");
  window.dispatchEvent(new Event("v09-session-change"));
}

type ReviewFailure = { failed_candidate_id?: number; succeeded?: number; failed?: number; pending_ids?: number[]; transaction?: "atomic" };
export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly reviewFailure?: ReviewFailure) { super(message); this.name = "ApiError"; }
}
function object(value: unknown): Record<string, unknown> | null { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null; }
function errorInfo(value: unknown, fallback: string) {
  const body = object(value);
  const details = object(object(body?.meta)?.details) ?? object(body?.detail);
  const message = typeof details?.message === "string" ? details.message : typeof body?.message === "string" && body.message !== "Request validation failed" ? body.message : typeof body?.detail === "string" ? body.detail : fallback;
  const failure: ReviewFailure = {};
  for (const key of ["failed_candidate_id", "succeeded", "failed"] as const) {
    if (typeof details?.[key] === "number" && Number.isSafeInteger(details[key]) && details[key] >= 0) failure[key] = details[key];
  }
  if (Array.isArray(details?.pending_ids)) failure.pending_ids = details.pending_ids.filter((id): id is number => typeof id === "number" && Number.isSafeInteger(id) && id > 0).slice(0, 50);
  if (details?.transaction === "atomic") failure.transaction = "atomic";
  const context = failure.failed_candidate_id != null ? " · 失败候选 #" + failure.failed_candidate_id : "";
  const count = failure.succeeded != null ? " · 成功 " + failure.succeeded + " 条" : "";
  return { message: message + context + count, failure: Object.keys(failure).length ? failure : undefined };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init?.headers) new Headers(init.headers).forEach((value, name) => {
    if (!["authorization", "content-type"].includes(name.toLowerCase())) headers[name] = value;
  });
  const stored = token();
  if (stored) headers.Authorization = `Bearer ${stored}`;
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (token() !== stored) throw new Error("登录账号已改变，请重试。");
  if (!response.ok) {
    if (response.status === 401 && stored && token() === stored) setToken(null);
    const detail: unknown = await response.json().catch(() => null);
    const fallback = response.status === 401 ? "登录已过期，请重新登录后提交。"
      : response.status === 429 ? "提交过于频繁，请稍后再试。"
      : response.status === 422 ? "请检查填写内容和来源网址。" : "操作失败，请稍后重试。";
    if (token() !== stored && response.status !== 401) throw new Error("登录账号已改变，请重试。");
    const info = errorInfo(detail, fallback);
    throw new ApiError(info.message, response.status, info.failure);
  }
  const body = (await response.json()) as { data: T };
  if (token() !== stored) throw new Error("登录账号已改变，请重试。");
  return body.data;
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const data = await apiFetch<AuthSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data;
}

export async function register(payload: {
  email: string;
  username: string;
  password: string;
  invite_code?: string | null;
}): Promise<AuthSession> {
  const data = await apiFetch<AuthSession>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setToken(data.token);
  return data;
}

export function me(): Promise<SessionUser> {
  return apiFetch<SessionUser>("/auth/me");
}

export function updateProfile(payload: Partial<V09Profile>): Promise<SessionUser> {
  return apiFetch<SessionUser>("/users/me/profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function myOverview(): Promise<V09Overview> {
  return apiFetch<V09Overview>("/users/me/overview");
}

export function competitionContext(competitionId: number, scope: { edition_id?: number; university_id?: number; college_id?: number } = {}): Promise<{ found: boolean; item?: V09Item }> {
  const query = new URLSearchParams();
  Object.entries(scope).forEach(([key, value]) => { if (value != null) query.set(key, String(value)); });
  return apiFetch(`/users/me/competitions/${competitionId}/context?${query}`);
}

export function myCalendarEvents(): Promise<
  { competition_id: number; name: string; deadline: string; deadline_label: string }[]
> {
  return apiFetch("/users/me/calendar-events");
}

export function setFavorite(competitionId: number, favorite: boolean): Promise<unknown> {
  return apiFetch(`/users/me/favorites${favorite ? "" : `/${competitionId}`}`, {
    method: favorite ? "POST" : "DELETE",
    body: favorite ? JSON.stringify({ competition_id: competitionId }) : undefined,
  });
}

export function setStatus(competitionId: number, status: string): Promise<unknown> {
  return apiFetch(`/users/me/competitions/${competitionId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

export function universityColleges(universityId: number): Promise<{ id: number; name: string }[]> {
  return apiFetch(`/directory/universities/${universityId}/colleges`);
}

export function collegeMajors(_collegeId: number): Promise<{ id: number; name: string }[]> {
  return apiFetch(`/directory/colleges/${_collegeId}/majors`);
}

export function interestOptions(): Promise<{ label: string; tags: string[] }[]> {
  return apiFetch("/directory/interest-options");
}

export type V09Notification = {
  id: number;
  type: string;
  title: string;
  content?: string | null;
  competition_id?: number | null;
  competition_edition_id?: number | null;
  is_read: boolean;
  created_at?: string | null;
};

export function notifications(category?: string): Promise<{ items: V09Notification[]; unread: number }> {
  return apiFetch(`/users/me/notifications${category ? `?category=${category}` : ""}`);
}

export function unreadNotifications(): Promise<{ unread: number }> {
  return apiFetch("/users/me/notifications/unread-count");
}

export function markNotificationRead(id: number): Promise<{ updated: boolean }> {
  return apiFetch(`/users/me/notifications/${id}/read`, { method: "POST" });
}

export function submitCorrection(payload: {
  competition_id: number;
  competition_edition_id?: number | null;
  correction_type: string;
  description: string;
  proposed_value?: string | null;
  source_url?: string | null;
}): Promise<{ id: number; status: string }> {
  return apiFetch("/users/me/corrections", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitFeedback(payload: { category: string; content: string; url?: string }): Promise<{ id: number }> {
  return apiFetch("/beta-feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function adminSummary(): Promise<Record<string, number>> {
  return apiFetch("/admin/review/summary");
}

export type ListPage = { limit?: number; offset?: number };
function listQuery(page: ListPage = {}, status?: string): string {
  const query = new URLSearchParams({ limit: String(page.limit ?? 21), offset: String(page.offset ?? 0) });
  if (status) query.set("status", status);
  return query.toString();
}

export function adminCorrections(status?: string, page?: ListPage): Promise<AdminCorrection[]> {
  return apiFetch(`/admin/review/corrections?${listQuery(page, status)}`);
}

export function adminReviewCorrection(id: number, status: string, note?: string, fields?: { competition_edition_id?: number; new_deadline?: string }): Promise<{ id: number; status: string }> {
  return apiFetch(`/admin/review/corrections/${id}`, {
    method: "PUT",
    body: JSON.stringify({ status, note: note ?? null, ...fields }),
  });
}

export function adminLeads(page?: ListPage): Promise<AdminLead[]> {
  return apiFetch(`/admin/review/leads?${listQuery(page)}`);
}

export function adminReviewLead(id: number, status: string): Promise<{ id: number; needs_review: boolean }> {
  return apiFetch(`/admin/review/leads/${id}`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

export function adminUpdates(page?: ListPage): Promise<CompetitionUpdateEvent[]> {
  return apiFetch(`/admin/review/updates?${listQuery(page)}`);
}

export function adminCandidateFacts(page?: ListPage): Promise<AdminCandidateFact[]> {
  return apiFetch(`/admin/review/candidate-facts?${listQuery(page)}`);
}

export function adminFeedback(page?: ListPage): Promise<AdminFeedback[]> {
  return apiFetch(`/admin/review/feedback?${listQuery(page)}`);
}

export type Supplement = { id: number; field_review_id?: number | null; kind: string; title: string; description: string; source_url?: string | null; status: string; review_note?: string | null; created_at: string };
export type MyCorrection = { id: number; competition_id: number; competition_edition_id?: number | null; correction_type: string; description: string; status: string; review_note?: string | null; created_at: string };
export function submitSupplement(payload: { kind: string; title: string; description: string; source_url?: string | null }): Promise<Supplement> {
  return apiFetch("/users/me/supplements", { method: "POST", body: JSON.stringify(payload) });
}
export function mySupplements(page?: ListPage): Promise<Supplement[]> { return apiFetch(`/users/me/supplements?${listQuery(page)}`); }
export function myCorrections(page?: ListPage): Promise<MyCorrection[]> { return apiFetch(`/users/me/corrections?${listQuery(page)}`); }
export function adminSupplements(status?: string, page?: ListPage): Promise<Supplement[]> { return apiFetch(`/admin/review/supplements?${listQuery(page, status)}`); }
export function adminReviewSupplement(id: number, status: string, note: string): Promise<Supplement> {
  return apiFetch(`/admin/review/supplements/${id}`, { method: "PUT", body: JSON.stringify({ status, note }) });
}
