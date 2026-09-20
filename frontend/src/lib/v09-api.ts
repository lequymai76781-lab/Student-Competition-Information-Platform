const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

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
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const stored = token();
  if (stored) headers.Authorization = `Bearer ${stored}`;
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(detail || `HTTP ${response.status}`);
  }
  const body = (await response.json()) as { data: T };
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

export function competitionContext(competitionId: number): Promise<{ found: boolean; item?: V09Item }> {
  return apiFetch(`/users/me/competitions/${competitionId}/context`);
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

export function adminCorrections(status?: string): Promise<any[]> {
  return apiFetch(`/admin/review/corrections${status ? `?status=${status}` : ""}`);
}

export function adminReviewCorrection(id: number, status: string, note?: string): Promise<any> {
  return apiFetch(`/admin/review/corrections/${id}`, {
    method: "PUT",
    body: JSON.stringify({ status, note: note ?? null }),
  });
}

export function adminLeads(): Promise<any[]> {
  return apiFetch("/admin/review/leads");
}

export function adminReviewLead(id: number, status: string): Promise<any> {
  return apiFetch(`/admin/review/leads/${id}`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

export function adminUpdates(): Promise<any[]> {
  return apiFetch("/admin/review/updates");
}

export function adminCandidateFacts(): Promise<any[]> {
  return apiFetch("/admin/review/candidate-facts");
}

export function adminFeedback(): Promise<any[]> {
  return apiFetch("/admin/review/feedback");
}
