import { ensureAuth, isAuthPublic, setToken } from "@/lib/auth";
import { getUserId } from "@/lib/user";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "https://tilko-api.onrender.com";

export function humanizeNetworkError(err: unknown, fallback = "Bağlantı hatası"): string {
  const message =
    err instanceof Error
      ? err.message
      : typeof err === "string"
        ? err
        : String(err ?? "");
  const name =
    typeof DOMException !== "undefined" && err instanceof DOMException
      ? err.name
      : err instanceof Error
        ? err.name
        : "";
  const blob = `${name} ${message}`.toLowerCase();
  if (
    name === "AbortError" ||
    name === "TimeoutError" ||
    /abort|timeout|timed\s*out|zaman\s*aşım|request timed|yavaş kaldı|gecikti/i.test(blob)
  ) {
    return "Analiz şu an yoğun. Biraz sonra tekrar dene.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(blob)) {
    return "API'ye ulaşılamadı. İnterneti kontrol et veya biraz sonra dene.";
  }
  if (
    /\b429\b|rate\s*limit|too\s*many\s*requests|çok\s*fazla\s*istek/i.test(blob)
  ) {
    return "Çok hızlı denendi. 20–30 saniye bekle, sonra tekrar giriş yap.";
  }
  if (/request timed out\.?/i.test(message.trim())) {
    return "Analiz şu an yoğun. Biraz sonra tekrar dene.";
  }
  return message.trim() || fallback;
}

/** Render'ı uyandır; analizden önce en fazla ~8 sn bekle, takılma. */
export async function wakeApi(): Promise<void> {
  if (typeof window !== "undefined") {
    try {
      const last = Number(window.sessionStorage.getItem("tilko_api_wake_at") || 0);
      if (Date.now() - last < 120_000) return;
    } catch {
      /* ignore */
    }
  }
  try {
    await Promise.race([
      fetch(`${API_BASE}/health`, { method: "GET", cache: "no-store" }),
      new Promise((resolve) => setTimeout(resolve, 8_000)),
    ]);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("tilko_api_wake_at", String(Date.now()));
    }
  } catch {
    /* analiz yine denenecek */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string>) || {}),
    };
    if (!isAuthPublic(path)) {
      const token = await ensureAuth(API_BASE, getUserId());
      headers.Authorization = `Bearer ${token}`;
    }
    // Admin anahtarı kayıtlıysa analiz kredi düşürmez.
    if (typeof window !== "undefined" && path.startsWith("/analyze")) {
      const adminSecret = window.localStorage.getItem("tilko_admin_secret") || "";
      if (adminSecret.trim()) {
        headers["X-Admin-Secret"] = adminSecret.trim();
      }
    }
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
    });
    if (response.status === 401 && !isAuthPublic(path)) {
      setToken("");
      const token = await ensureAuth(API_BASE, getUserId());
      headers.Authorization = `Bearer ${token}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...init, headers });
      return await readJson<T>(retry);
    }
    return await readJson<T>(response);
  } catch (err) {
    throw new Error(humanizeNetworkError(err));
  }
}

function formatApiDetail(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const row = item as { msg?: unknown; message?: unknown; loc?: unknown };
          const where = Array.isArray(row.loc)
            ? row.loc.filter((part) => part !== "body").join(".")
            : "";
          const msg = String(row.msg || row.message || "").trim();
          if (msg && where) return `${where}: ${msg}`;
          return msg;
        }
        return "";
      })
      .filter(Boolean)
      .join(" ");
  }
  if (typeof detail === "object") {
    const row = detail as { message?: unknown; msg?: unknown; detail?: unknown };
    if (typeof row.message === "string") return row.message;
    if (typeof row.msg === "string") return row.msg;
    if (typeof row.detail === "string") return row.detail;
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return "";
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 429) {
      throw new Error(
        "Çok hızlı denendi. 20–30 saniye bekle, sonra tekrar giriş yap.",
      );
    }
    const detail = formatApiDetail((data as { detail?: unknown }).detail);
    throw new Error(
      humanizeNetworkError(
        detail || `İstek başarısız (${response.status})`,
        `İstek başarısız (${response.status})`,
      ),
    );
  }
  return data as T;
}

export type TeacherPersona = {
  catchphrases: string[];
  tone: string;
};

export type NoteItem = {
  id: string;
  title: string;
  text: string;
  key_points: string[];
  mnemonic: string;
  exam_tip: string;
  timestamp_label: string;
  video_url_with_t: string;
};

export type PremiseItem = {
  id: string;
  text: string;
  is_correct: boolean;
  why: string;
};

export type QuestionItem = {
  id: string;
  text: string;
  options: Record<string, string>;
  correct: string;
  explanation: string;
  trap_explanation: string;
  topic: string;
  difficulty: string;
  timestamp_label: string;
  video_url_with_t: string;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  fen_branch?: string;
  misconception_tag?: string;
  step_by_step_solution?: string[];
  shortcut_tactic?: string;
  premises?: PremiseItem[];
};

export type AnalyzeResponse = {
  notes: NoteItem[];
  questions: QuestionItem[];
  cached: boolean;
  teacher_persona: TeacherPersona;
  video_id?: string;
  video_url?: string;
  subject?: string | null;
  job_id?: string;
  job_status?: "running" | "done" | "error" | string;
  job_error?: string;
  chunks_done?: number;
  chunks_total?: number;
  ai_credits_left: number;
  ai_credit_limit: number;
  is_premium: boolean;
  is_in_trial_period: boolean;
  is_ad_tier: boolean;
  daily_ad_credits: number;
  daily_ad_limit: number;
  trial_days_left: number;
};

export type TrapItem = {
  id: number;
  question_id?: string;
  question_text: string;
  options: Record<string, string>;
  correct: string;
  chosen: string;
  explanation: string;
  distractor_analysis: string;
  teacher_note: string;
  topic: string;
  time_spent_seconds: number;
  time_trap_triggered: boolean;
  review_count: number;
  next_review_date: string | null;
  subject_type?: string;
  shortcut_tactic?: string;
  step_by_step_solution?: string[];
  premises?: PremiseItem[];
  misconception_tag?: string;
  fen_branch?: string;
  is_yks_fen?: boolean;
};

export type PrizeSlice = {
  monthly_rank: number | null;
  is_free_next_month: boolean;
  discount_percentage: number;
  badge: string | null;
  tier: string | null;
  source_month: string | null;
  projected: boolean;
  correct_count?: number;
  avg_time_ms?: number;
};

export type PrizeView = {
  live: PrizeSlice;
  settled: PrizeSlice;
  badge: string | null;
  discount_percentage: number;
  is_free_next_month: boolean;
  monthly_rank: number | null;
  total_active_users?: number;
  prize_stage?: string;
  prize_banner?: string;
};

export type RecommendedVideo = {
  title: string;
  topic: string;
  url: string;
};

export type Progress = {
  display_name: string;
  xp: number;
  level: number;
  title: string;
  title_emoji: string;
  xp_to_next: number;
  current_streak: number;
  longest_streak: number;
  traps_logged: number;
  traps_cleared: number;
  prize: PrizeView;
  ai_credits_left: number;
  ai_credit_limit: number;
  is_premium: boolean;
  is_in_trial_period: boolean;
  is_ad_tier: boolean;
  daily_ad_credits: number;
  daily_ad_limit: number;
  trial_days_left: number;
  is_tested: boolean;
  baseline_score: number;
  checkup_due: boolean;
  weak_topics: string[];
  analysis_summary: string;
  recommended_videos: RecommendedVideo[];
  exam_target: string;
  exam_label: string;
  is_onboarded: boolean;
  target_score: number;
  target_is_set: boolean;
  current_score: number;
  progress_pct: number;
  days_until_exam: number;
  exam_date: string;
  exam_date_label?: string;
  today?: string;
  today_label?: string;
  countdown_headline?: string;
  subscription_status?: string;
  subscription_product_id?: string;
  subscription_expires_at?: string | null;
  role?: string;
  teacher_id?: string;
  teacher_name?: string;
  dashboard?: string;
};

export type DiagnosticQuestion = {
  id: string;
  topic: string;
  question_text: string;
  options: Record<string, string>;
};

export type DiagnosticReport = {
  is_tested: boolean;
  score: number;
  correct_count: number;
  total: number;
  weak_topics: string[];
  strong_topics: string[];
  analysis_summary: string;
  net_range: string;
  topic_breakdown: Record<string, { correct: number; total: number; ratio: number }>;
  recommended_videos: RecommendedVideo[];
};

export type CheckupReport = {
  score: number;
  correct_count: number;
  total: number;
  weak_topics: string[];
  improvement_summary: string;
  score_delta: number | null;
  previous_score: number | null;
  checkup_date: string;
  topic_breakdown: Record<string, { correct: number; total: number; ratio: number }>;
  recommended_videos: RecommendedVideo[];
};

export type ProgressPoint = {
  date: string;
  score: number;
  weak_topics: string[];
  improvement_summary: string;
};

export function analyzeVideo(payload: {
  video_url: string;
  user_id: string;
  subject?: string;
  question_count: number;
  ad_watched?: boolean;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  transcript_lines?: { start: number; text: string }[];
}) {
  // AbortSignal yok: tarayıcı "Request timed out" basmasın; API zaten hemen job döner.
  return request<AnalyzeResponse>("/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAnalyzeJob(jobId: string) {
  // Abort yok: Render uyurken poll düşmesin; job arka planda sürer.
  return request<AnalyzeResponse>(`/analyze/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelAnalyzeJob(jobId: string) {
  return request<{ ok: boolean; job_id: string; status: string }>(
    `/analyze/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST", body: "{}" },
  );
}

export type SavedNoteItem = NoteItem & {
  saved_id: number;
  subject: string;
  video_id?: string;
  session_label?: string;
  video_url: string;
  created_at?: string | null;
};

export type SavedQuestionItem = QuestionItem & {
  saved_id: number;
  subject: string;
  video_id?: string;
  session_label?: string;
  video_url: string;
  created_at?: string | null;
  teacher_persona?: TeacherPersona;
};

export type NotebookSessionItem = {
  id: number;
  subject: string;
  video_id: string;
  video_url: string;
  label: string;
  note_count: number;
  question_count: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type NotebookResponse = {
  user_id: string;
  subject: string | null;
  subjects: { name: string; note_count: number; question_count: number }[];
  sessions?: NotebookSessionItem[];
  notes: SavedNoteItem[];
  questions: SavedQuestionItem[];
};

export function listNotebook(userId: string, subject?: string) {
  const query = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return request<NotebookResponse>(`/notebook/${userId}${query}`);
}

export function renameNotebookSession(input: {
  user_id: string;
  subject: string;
  video_id: string;
  label: string;
  video_url?: string;
}) {
  return request<{ ok: boolean; session: NotebookSessionItem }>("/notebook/session", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function downloadNotebookPdf(input: {
  userId: string;
  subject: string;
  videoId: string;
  filename?: string;
}) {
  const path =
    `/notebook/${encodeURIComponent(input.userId)}/pdf` +
    `?subject=${encodeURIComponent(input.subject)}` +
    `&video_id=${encodeURIComponent(input.videoId)}`;
  const headers: Record<string, string> = {};
  if (!isAuthPublic(path)) {
    const token = await ensureAuth(API_BASE, getUserId());
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "PDF indirilemedi");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(input.filename || "tilko-notlar").replace(/[^\w\-ğüşıöçĞÜŞİÖÇ ]+/gi, "").trim() || "tilko-notlar"}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function unlockAd(userId: string) {
  return request<{
    ok: boolean;
    is_ad_tier: boolean;
    daily_ad_credits: number;
    daily_ad_limit: number;
    is_in_trial_period: boolean;
  }>("/ads/unlock", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function listTraps(userId: string) {
  return request<{ traps: TrapItem[] }>(`/traps/${userId}`);
}

export function dailyMissions(userId: string) {
  return request<{ due_count: number; traps: TrapItem[] }>(
    `/daily_missions/${userId}`,
  );
}

export function saveTrap(payload: {
  user_id: string;
  question_text: string;
  chosen: string;
  correct: string;
  explanation: string;
  trap_explanation?: string;
  teacher_persona?: TeacherPersona;
  topic: string;
  question_id: string;
  options: Record<string, string>;
  time_spent_seconds: number;
  subject_type?: string;
  shortcut_tactic?: string;
  step_by_step_solution?: string[];
  premises?: PremiseItem[];
  misconception_tag?: string;
  fen_branch?: string;
  is_yks_fen_question?: boolean;
}) {
  return request<{
    warning: string;
    time_trap_triggered: boolean;
    trap: TrapItem;
  }>(
    "/save_trap",
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function completeTrap(payload: {
  user_id: string;
  trap_id: number;
  chosen: string;
}) {
  return request<{
    correct: boolean;
    message: string;
    game: { xp_gained: number; streak: number; notebook_cleared: boolean };
  }>("/complete_trap", { method: "POST", body: JSON.stringify(payload) });
}

export function getProgress(userId: string) {
  return request<Progress>(`/progress/${userId}`);
}

export type ExamTargetResult = {
  user_id: string;
  exam_target: string;
  exam_label: string;
  is_onboarded: boolean;
  is_tested?: boolean;
  reset?: boolean;
  title: string;
  message: string;
  days_left?: number;
  headline?: string;
  exam_date?: string;
  exam_date_label?: string;
  today?: string;
  today_label?: string;
};

export function setExamTarget(userId: string, examTarget: string) {
  return request<ExamTargetResult>("/user/set-exam-target", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, exam_target: examTarget }),
  });
}

export type ExamCountdown = {
  exam_target: string;
  exam_label: string;
  exam_date: string;
  exam_date_label?: string;
  today?: string;
  today_label?: string;
  days_left: number;
  headline: string;
};

export function getExamCountdown(userId: string) {
  return request<ExamCountdown>(
    `/user/exam-countdown?user_id=${encodeURIComponent(userId)}`,
  );
}

export type TargetScoreResult = {
  user_id: string;
  target_score: number;
  title: string;
  message: string;
};

export function setTargetScore(userId: string, targetScore: number) {
  return request<TargetScoreResult>("/user/set-target-score", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, target_score: targetScore }),
  });
}

export type MotivationalQuote = {
  user_id: string;
  quote: string;
  title: string;
  exam_target: string;
  exam_label: string;
  date: string;
};

export function getMotivationalQuote(userId: string) {
  return request<MotivationalQuote>(
    `/motivational-quote?user_id=${encodeURIComponent(userId)}`,
  );
}

export type PenaltyStatus = {
  user_id: string;
  is_penalized: boolean;
  penalty_clear_count: number;
  needed: number;
  trap: TrapItem | null;
  message?: string;
};

export type PenaltyAnswer = {
  correct: boolean;
  streak: number;
  unlocked: boolean;
  is_penalized: boolean;
  needed: number;
  trap: TrapItem | null;
  message: string;
};

export function applyPenalty(userId: string, elapsedSeconds = 0) {
  return request<PenaltyStatus>("/api/penalty", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, elapsed_seconds: elapsedSeconds }),
  });
}

export function getPenaltyStatus(userId: string) {
  return request<PenaltyStatus>(`/api/penalty/${userId}`);
}

export function answerPenalty(payload: {
  user_id: string;
  trap_id: number;
  chosen: string;
}) {
  return request<PenaltyAnswer>("/api/penalty/answer", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function clearPenalty(userId: string) {
  return request<PenaltyStatus>("/api/clear_penalty", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export type KurnazEntry = {
  rank: number;
  user_id: string;
  display_name: string;
  time_spent_ms: number;
  title: string;
  emoji: string;
  badge: string;
  prize_badge: string | null;
  monthly_rank: number | null;
};

export type DailyChallenge = {
  id: number;
  question_text: string;
  options: Record<string, string>;
  date: string | null;
  already_attempted: boolean;
  result: DailyChallengeResult | null;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  fen_branch?: string;
  premises?: PremiseItem[];
};

export type DailyChallengeResult = {
  challenge_id: number;
  is_correct: boolean;
  already_attempted: boolean;
  time_spent_ms: number;
  trap_explanation: string;
  wrong_count: number;
  wrong_message: string | null;
  rank: number | null;
  leaderboard: KurnazEntry[];
  xp_gained: number;
  xp: number;
  title: string;
  title_emoji: string;
  is_suspicious: boolean;
  is_cheated: boolean;
  eligible: boolean;
  suspicious_reason: string | null;
  subject_type?: string;
  shortcut_tactic?: string;
  step_by_step_solution?: string[];
  premises?: PremiseItem[];
  misconception_tag?: string;
  fen_branch?: string;
  is_yks_fen_question?: boolean;
};

export type DailyChallengeLeaderboard = {
  challenge_id: number;
  date: string | null;
  title: string;
  entries: KurnazEntry[];
  viewer_rank: number | null;
  total_active_users: number;
  prize_stage: string;
  prize_banner: string;
};

export function getDailyChallenge(userId: string) {
  return request<DailyChallenge>(
    `/daily-challenge?user_id=${encodeURIComponent(userId)}`,
  );
}

export function startDailyChallenge(payload: {
  user_id: string;
  challenge_id: number;
  device_id: string;
}) {
  return request<{
    challenge_id: number;
    started_at: string | null;
    already_attempted: boolean;
  }>("/daily-challenge/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitDailyChallenge(payload: {
  user_id: string;
  chosen: string;
  challenge_id: number;
  device_id: string;
}) {
  return request<DailyChallengeResult>("/daily-challenge/submit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getKurnazLeaderboard(userId: string) {
  return request<DailyChallengeLeaderboard>(
    `/daily-challenge/leaderboard?user_id=${encodeURIComponent(userId)}`,
  );
}

export function completePomodoro(userId: string, sessionId: string) {
  return request<{
    xp_gained: number;
    xp: number;
    level: number;
    title: string;
    title_emoji: string;
    already: boolean;
  }>("/api/pomodoro/complete", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, session_id: sessionId }),
  });
}

export function getDiagnosticExam(userId: string, kind: "baseline" | "checkup") {
  return request<{ kind: string; questions: DiagnosticQuestion[] }>(
    `/diagnostic/exam?kind=${kind}&user_id=${encodeURIComponent(userId)}`,
  );
}

export function submitDiagnostic(
  userId: string,
  answers: { question_id: string; chosen: string }[],
) {
  return request<DiagnosticReport>("/diagnostic/submit", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, answers }),
    signal: AbortSignal.timeout(180_000),
  });
}

export function submitCheckup(
  userId: string,
  answers: { question_id: string; chosen: string }[],
) {
  return request<CheckupReport>("/diagnostic/checkup-submit", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, answers }),
  });
}

export type DynamicExamQuestion = DiagnosticQuestion & {
  difficulty?: string;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  fen_branch?: string;
  premises?: PremiseItem[];
};

export type DynamicExamCatalog = {
  user_id: string;
  exam_target: string;
  exam_label: string;
  family: string;
  subjects: string[];
  question_counts: number[];
  seconds_per_question: number;
};

export type DynamicExamSession = {
  exam_id: number;
  status: string;
  exam_target: string;
  exam_label: string;
  subjects: string[];
  question_count: number;
  duration_seconds: number;
  remaining_seconds: number;
  started_at: string | null;
  questions: DynamicExamQuestion[];
  trap_blend: boolean;
  osym_dna: boolean;
  report: DynamicExamReport | null;
};

export type DynamicExamReview = {
  question_id: string;
  topic: string;
  question_text: string;
  options: Record<string, string>;
  chosen: string;
  correct: string;
  is_correct: boolean;
  explanation: string;
  trap_explanation: string;
  subject_type?: string;
  is_yks_fen_question?: boolean;
  fen_branch?: string;
  misconception_tag?: string;
  step_by_step_solution?: string[];
  shortcut_tactic?: string;
  premises?: PremiseItem[];
};

export type DynamicExamReport = {
  exam_id: number;
  already: boolean;
  score: number;
  correct_count: number;
  total: number;
  weak_topics: string[];
  strong_topics: string[];
  topic_breakdown: Record<string, { correct: number; total: number; ratio: number }>;
  net_range: string;
  coach_summary: string;
  weakness_analysis: string;
  prescription: string;
  traps_hit: string[];
  reviews: DynamicExamReview[];
  recommended_videos: RecommendedVideo[];
  is_cheated: boolean;
  traps_saved: number;
  time_spent_seconds: number;
  exam_target: string;
  exam_label: string;
  subjects: string[];
  xp_gained: number;
  xp: number;
  level: number;
  title: string;
  title_emoji: string;
};

export function getDynamicExamCatalog(userId: string, examTarget?: string) {
  const extra = examTarget ? `&exam_target=${encodeURIComponent(examTarget)}` : "";
  return request<DynamicExamCatalog>(
    `/exam/catalog?user_id=${encodeURIComponent(userId)}${extra}`,
  );
}

export function generateDynamicExam(payload: {
  user_id: string;
  exam_target?: string;
  subjects: string[];
  question_count: number;
}) {
  return request<DynamicExamSession>("/exam/generate-dynamic", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getDynamicExam(userId: string, examId: number) {
  return request<DynamicExamSession>(
    `/exam/dynamic/${examId}?user_id=${encodeURIComponent(userId)}`,
  );
}

export function submitDynamicExam(payload: {
  user_id: string;
  exam_id: number;
  answers: { question_id: string; chosen: string }[];
  time_spent_seconds?: number;
}) {
  return request<DynamicExamReport>("/exam/submit-dynamic", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProgressHistory(userId: string) {
  return request<{ user_id: string; points: ProgressPoint[] }>(
    `/diagnostic/progress-history?user_id=${encodeURIComponent(userId)}`,
  );
}

export type QuestionReport = {
  id: number;
  question_id: string;
  status: string;
  message: string;
};

export function reportQuestion(payload: {
  user_id: string;
  question_id: string;
  reason_text: string;
}) {
  return request<QuestionReport>("/questions/report", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type MistakeTypeShare = {
  type: string;
  count: number;
  rate: number;
};

export type MistakeDoctorReport = {
  user_id: string;
  title: string;
  trap_count: number;
  types: MistakeTypeShare[];
  dominant: string | null;
  summary: string;
  prescription: string;
  weak_topics: string[];
  source: string;
};

export function getMistakeDoctor(userId: string) {
  return request<MistakeDoctorReport>(
    `/analytics/mistake-doctor?user_id=${encodeURIComponent(userId)}`,
  );
}

export type FeedbackCategory = "feature" | "ui_ux" | "general";

export type FeedbackSubmit = {
  id: number;
  category: FeedbackCategory;
  status: string;
  message: string;
};

export function submitFeedback(payload: {
  user_id: string;
  category: FeedbackCategory;
  message: string;
}) {
  return request<FeedbackSubmit>("/feedback/submit", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type AdminFeedbackItem = {
  id: number;
  user_id: string;
  display_name: string;
  email: string;
  phone: string;
  category: string;
  category_label: string;
  message: string;
  status: string;
  created_at: string | null;
};

export async function listAdminFeedback(secret: string, status = "") {
  const headers = await adminHeaders(secret);
  const params = new URLSearchParams({ limit: "150" });
  if (status.trim()) params.set("status", status.trim());
  const response = await fetch(`${API_BASE}/admin/feedback?${params}`, { headers });
  return readJson<{ items: AdminFeedbackItem[]; count: number }>(response);
}

export async function setAdminFeedbackStatus(
  secret: string,
  feedbackId: number,
  status: "pending" | "done" | "archived",
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(
    `${API_BASE}/admin/feedback/${encodeURIComponent(String(feedbackId))}/status`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ status }),
    },
  );
  return readJson<{ id: number; status: string; message: string }>(response);
}

export type SubscriptionPlan = {
  id: string;
  label: string;
  period: string;
  days: number;
  price_try: number;
  price_label: string;
};

export type SubscriptionStatus = {
  ok: boolean;
  is_premium: boolean;
  subscription_status: string;
  product_id: string;
  expires_at: string | null;
  sandbox: boolean;
  package_name: string;
  plans: SubscriptionPlan[];
  message: string;
};

export function getSubscriptionStatus(userId: string) {
  return request<SubscriptionStatus>(
    `/subscription/status?user_id=${encodeURIComponent(userId)}`,
  );
}

export async function listAdminPlans(secret: string) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/plans`, { headers });
  return readJson<{
    ok: boolean;
    plans: SubscriptionPlan[];
    message: string;
  }>(response);
}

export async function updateAdminPlans(
  secret: string,
  plans: { product_id: string; price_try?: number; label?: string }[],
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/plans`, {
    method: "POST",
    headers,
    body: JSON.stringify({ plans }),
  });
  return readJson<{
    ok: boolean;
    plans: SubscriptionPlan[];
    message: string;
  }>(response);
}

export function verifySubscription(payload: {
  user_id: string;
  product_id: string;
  purchase_token: string;
  order_id?: string;
  platform?: string;
}) {
  return request<SubscriptionStatus>("/subscription/verify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type RagStatus = {
  docs: number;
  chunks: number;
  highlights: number;
  archive_dir: string;
  style: {
    stems: string[];
    traps: string[];
    topics: string[];
    years: string;
    revision: number;
  };
  topic_signals: { topic: string; weight: number; source: string }[];
};

export type ArchiveFeedResult = {
  ok: boolean;
  processed: number;
  results: {
    filename?: string;
    source_url?: string;
    skipped?: boolean;
    chunks?: number;
    error?: string;
    exam_year?: number;
  }[];
  style_revision: number;
  signals: { topic: string; weight: number; source: string }[];
};

function adminHeaders(secret: string, json = true): Promise<Record<string, string>> {
  // Admin uçları yalnızca X-Admin-Secret ister; giriş zorunlu değil.
  const headers: Record<string, string> = {
    "X-Admin-Secret": secret,
  };
  if (json) headers["Content-Type"] = "application/json";
  return Promise.resolve(headers);
}

export type ExamScheduleItem = {
  exam_target: string;
  label: string;
  exam_date: string;
  exam_date_label?: string;
  days_remaining: number;
  message?: string;
};

export type ExamScheduleList = {
  exams: ExamScheduleItem[];
  count: number;
  today: string;
  today_label: string;
  today_override: boolean;
  real_today: string;
  real_today_label: string;
  message?: string;
};

export async function listExamSchedules(secret: string) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/exams/list`, { headers });
  return readJson<ExamScheduleList>(response);
}

export async function updateExamToday(
  secret: string,
  payload: { exam_date?: string; reset?: boolean },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/exams/today`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<ExamScheduleList>(response);
}

export async function updateExamSchedule(
  secret: string,
  payload: { exam_target: string; exam_date: string },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/exams/update`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<ExamScheduleItem>(response);
}

export async function getRagStatus(secret: string, examTarget = "") {
  const headers = await adminHeaders(secret);
  const query = examTarget
    ? `?exam_target=${encodeURIComponent(examTarget)}`
    : "";
  const response = await fetch(`${API_BASE}/admin/rag-status${query}`, { headers });
  return readJson<RagStatus>(response);
}

export async function feedOsymArchives(
  secret: string,
  payload: {
    exam_target?: string;
    exam_year?: number;
    files?: File[];
    urls?: string[];
    scan_inbox?: boolean;
  },
) {
  const files = payload.files || [];
  const urls = (payload.urls || []).map((item) => item.trim()).filter(Boolean);
  if (files.length) {
    const headers = await adminHeaders(secret, false);
    const form = new FormData();
    if (payload.exam_target) form.append("exam_target", payload.exam_target);
    if (payload.exam_year) form.append("exam_year", String(payload.exam_year));
    form.append("scan_inbox", payload.scan_inbox ? "true" : "false");
    if (urls.length) form.append("urls", urls.join("\n"));
    for (const file of files) form.append("files", file);
    const response = await fetch(`${API_BASE}/admin/feed-osym-archives`, {
      method: "POST",
      headers,
      body: form,
    });
    return readJson<ArchiveFeedResult>(response);
  }
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/feed-osym-archives`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      exam_target: payload.exam_target || "",
      exam_year: payload.exam_year || 0,
      urls,
      scan_inbox: Boolean(payload.scan_inbox),
    }),
  });
  return readJson<ArchiveFeedResult>(response);
}

export type PromoQuote = {
  ok: boolean;
  code: string;
  discount_type: string;
  value: number;
  product_id: string;
  original_price: number;
  discount_amount: number;
  payable_amount: number;
  message: string;
  classroom_joined?: boolean;
  teacher_id?: string;
  teacher_name?: string;
  join_message?: string;
};

export type PromoRedemption = {
  user_id: string;
  product_id: string;
  original_price: number;
  discount_amount: number;
  payable_amount: number;
  used_at: string | null;
};

export type PromoCoupon = {
  id: number;
  code: string;
  discount_type: string;
  value: number;
  max_uses: number;
  used_count: number;
  remaining: number | null;
  used_by?: string[];
  expires_at: string | null;
  created_at: string | null;
  status: string;
  created_by_teacher_id?: string;
  enroll_to_class?: boolean;
  redemptions: PromoRedemption[];
};

export type PromoCreateResult = {
  ok: boolean;
  count: number;
  coupons: PromoCoupon[];
  message: string;
};

export function applyPromo(payload: {
  user_id: string;
  code: string;
  product_id?: string;
}) {
  return request<PromoQuote>("/billing/apply-promo", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createPromo(
  secret: string,
  payload: {
    code: string;
    discount_type: string;
    value: number;
    max_uses: number;
    quantity?: number;
    expires_at?: string;
    created_by_teacher_id?: string;
    enroll_to_class?: boolean;
  },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/promo/create`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<PromoCreateResult>(response);
}

export async function listPromos(secret: string) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/promo/list`, { headers });
  return readJson<{ coupons: PromoCoupon[]; count: number }>(response);
}

export type AdminCreditsGrant = {
  ok: boolean;
  user_id: string;
  ai_credits_left: number;
  ai_credit_limit: number;
  is_premium: boolean;
  is_in_trial_period: boolean;
  message: string;
};

export async function grantAdminCredits(
  secret: string,
  payload: {
    user_id: string;
    credits?: number | null;
    premium?: boolean | null;
    days?: number;
  },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/credits/grant`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<AdminCreditsGrant>(response);
}

export type ProEntitlementEvent = {
  id: number;
  user_id: string;
  action: string;
  source: string;
  days: number;
  starts_at: string | null;
  expires_at: string | null;
  actor: string;
  note: string;
  meta?: Record<string, unknown>;
  created_at: string | null;
};

export async function listProLogs(
  secret: string,
  opts?: { user_id?: string; limit?: number },
) {
  const headers = await adminHeaders(secret);
  const params = new URLSearchParams();
  if (opts?.user_id) params.set("user_id", opts.user_id);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const query = params.toString() ? `?${params}` : "";
  const response = await fetch(`${API_BASE}/admin/pro-logs${query}`, { headers });
  return readJson<{ events: ProEntitlementEvent[]; count: number }>(response);
}

export type AdminUserRow = {
  user_id: string;
  display_name: string;
  email: string;
  phone: string;
  exam_target: string;
  role: string;
  is_premium: boolean;
  subscription_status: string;
  subscription_expires_at: string | null;
  ai_credits_left: number;
  created_at: string | null;
  has_google: boolean;
  has_password?: boolean;
};

export async function listAdminUsers(secret: string, q = "") {
  const headers = await adminHeaders(secret);
  const query = q.trim() ? `?q=${encodeURIComponent(q.trim())}&limit=150` : "?limit=150";
  const response = await fetch(`${API_BASE}/admin/users${query}`, { headers });
  return readJson<{ users: AdminUserRow[]; count: number }>(response);
}

export async function grantAdminPro(
  secret: string,
  payload: { user_id: string; days?: number; revoke?: boolean },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/users/grant-pro`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<{
    ok: boolean;
    user_id: string;
    is_premium: boolean;
    subscription_status: string;
    subscription_expires_at: string | null;
    message: string;
  }>(response);
}

export type AuthSession = {
  access_token: string;
  token_type: string;
  user_id: string;
  role: string;
  display_name: string;
  dashboard: string;
};

export function loginAccount(payload: {
  user_id?: string;
  email?: string;
  phone?: string;
  password: string;
  role?: string;
  display_name?: string;
  exam_target?: string;
}) {
  return request<AuthSession>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginWithGoogle(payload: {
  id_token: string;
  role?: string;
  display_name?: string;
  exam_target?: string;
  link_user_id?: string;
}) {
  return request<AuthSession>("/auth/google", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function registerAccount(payload: {
  user_id?: string;
  email?: string;
  phone?: string;
  password: string;
  role?: string;
  display_name?: string;
  exam_target?: string;
}) {
  return request<AuthSession>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function forgotPassword(payload: { email?: string; phone?: string }) {
  return request<{
    ok: boolean;
    sent: boolean;
    channel: string;
    destination_hint: string;
    message: string;
    debug_code?: string;
  }>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resetPassword(payload: {
  email?: string;
  phone?: string;
  code: string;
  new_password: string;
}) {
  return request<{ ok: boolean; user_id: string; message: string }>(
    "/auth/reset-password",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function adminSetPassword(
  secret: string,
  payload: { user_id: string; new_password: string },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/users/set-password`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<{ ok: boolean; user_id: string; message: string }>(response);
}

export async function adminIssueResetCode(
  secret: string,
  payload: { user_id: string },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/users/reset-code`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<{
    ok: boolean;
    user_id: string;
    email: string;
    code: string;
    expires_in_minutes: number;
    email_sent: boolean;
    message: string;
  }>(response);
}

export async function adminDeleteUser(
  secret: string,
  payload: { user_id: string },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/users/delete`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<{ ok: boolean; user_id: string; message: string }>(response);
}

export async function adminUpdateUser(
  secret: string,
  payload: {
    user_id: string;
    display_name?: string | null;
    email?: string | null;
    phone?: string | null;
    exam_target?: string | null;
    new_password?: string | null;
  },
) {
  const headers = await adminHeaders(secret);
  const response = await fetch(`${API_BASE}/admin/users/update`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return readJson<{
    ok: boolean;
    user_id: string;
    display_name: string;
    email: string;
    phone: string;
    exam_target: string;
    has_password: boolean;
    message: string;
  }>(response);
}

export type TeacherStudentCard = {
  user_id: string;
  display_name: string;
  baseline_score: number;
  net_range: string;
  is_tested: boolean;
  trap_count: number;
  traps_cleared: number;
  xp: number;
  weak_topics: string[];
  exam_target: string;
  analysis_summary: string;
  rank: number;
};

export type TeacherClassroom = {
  teacher_id: string;
  teacher_name: string;
  role: string;
  student_count: number;
  class_average: number;
  students: TeacherStudentCard[];
  ranking: TeacherStudentCard[];
  hot_topics: { topic: string; hits: number; intensity: number }[];
};

export type TeacherStudentAnalysis = {
  student: TeacherStudentCard;
  doctor: MistakeDoctorReport;
  traps: {
    id: number;
    question_text: string;
    topic: string;
    chosen: string;
    correct: string;
    teacher_note: string;
    distractor_analysis: string;
    time_trap_triggered: boolean;
  }[];
  baseline: Record<string, unknown>;
  weak_topics: string[];
  analysis_summary: string;
};

export type TeacherAssignment = {
  id: number;
  teacher_id: string;
  title: string;
  topic: string;
  question_text: string;
  options: Record<string, string>;
  correct?: string;
  explanation?: string;
  assigned_count?: number;
  completed_count?: number;
  created_at: string | null;
  completed?: boolean;
};

export function getTeacherClassroom() {
  return request<TeacherClassroom>("/teacher/students");
}

export function getTeacherStudentAnalysis(studentId: string) {
  return request<TeacherStudentAnalysis>(
    `/teacher/student-analysis/${encodeURIComponent(studentId)}`,
  );
}

export function shareTeacherResource(payload: {
  title?: string;
  topic?: string;
  question_text: string;
  options: Record<string, string>;
  correct?: string;
  explanation?: string;
  student_ids?: string[];
}) {
  return request<TeacherAssignment>("/teacher/share-resource", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createTeacherPromo(payload: {
  code: string;
  discount_type: string;
  value: number;
  max_uses: number;
  quantity?: number;
  expires_at?: string;
  enroll_to_class?: boolean;
}) {
  return request<PromoCreateResult>("/teacher/promo/create", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listTeacherPromos() {
  return request<{ coupons: PromoCoupon[]; count: number }>("/teacher/promo/list");
}

export function listStudentAssignments() {
  return request<{
    assignments: TeacherAssignment[];
    count: number;
    teacher_id: string;
    teacher_name: string;
  }>("/student/assignments");
}

export function submitStudentAssignment(assignmentId: number, chosen: string) {
  return request<{
    ok: boolean;
    correct: boolean;
    message: string;
    answer: string;
    explanation: string;
  }>("/student/assignments/submit", {
    method: "POST",
    body: JSON.stringify({
      user_id: getUserId(),
      assignment_id: assignmentId,
      chosen,
    }),
  });
}
