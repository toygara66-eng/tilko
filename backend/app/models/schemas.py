from pydantic import BaseModel, Field, HttpUrl


class TeacherPersona(BaseModel):
    catchphrases: list[str] = Field(default_factory=list)
    tone: str = "öğretici, net"


class TranscriptLineIn(BaseModel):
    start: int = 0
    text: str = ""


class AnalyzeRequest(BaseModel):
    video_url: HttpUrl = Field(..., description="YouTube video bağlantısı")
    user_id: str = Field(..., min_length=1, description="Kota takibi için aday kimliği")
    subject: str | None = Field(
        default=None,
        description="Opsiyonel ders/konu etiketi (örn. Anayasa, Vatandaşlık)",
    )
    question_count: int = Field(default=10, ge=1, le=30)
    ad_watched: bool = Field(
        default=False,
        description="Reklamlı katmanda reklam izlendikten sonra True",
    )
    subject_type: str | None = Field(
        default=None,
        description="sozel veya sayisal — boşsa konudan çıkarılır",
    )
    is_yks_fen_question: bool = Field(
        default=False,
        description="TYT/AYT Fen ise öncüllü (I, II, III) soru üret",
    )
    transcript_lines: list[TranscriptLineIn] | None = Field(
        default=None,
        description="İstemcinin çektiği altyazı; doluysa sunucu YouTube'a gitmez",
        max_length=20000,
    )


class NoteItem(BaseModel):
    id: str
    title: str = Field(default="", description="Kavramın kısa adı")
    text: str = Field(..., description="Detaylı açıklama")
    key_points: list[str] = Field(default_factory=list)
    mnemonic: str = Field(default="", description="Akılda kalıcı hafıza tekniği")
    exam_tip: str = Field(default="", description="ÖSYM tuzağı uyarısı")
    timestamp: int = Field(..., description="Videonun başlangıcından itibaren saniye")
    timestamp_label: str = Field(..., description="mm:ss gösterim")
    video_url_with_t: str = Field(
        ...,
        description="Mobilde tıklanınca ilgili saniyeye giden YouTube URL",
    )


class PremiseItem(BaseModel):
    id: str = ""
    text: str = ""
    is_correct: bool = False
    why: str = ""


class QuestionItem(BaseModel):
    id: str
    text: str
    options: dict[str, str]
    correct: str
    explanation: str
    trap_explanation: str = Field(
        default="",
        description="Hoca üslubuyla kırmızı kalem notu",
    )
    topic: str = Field(default="")
    difficulty: str = Field(default="")
    timestamp: int
    timestamp_label: str
    video_url_with_t: str
    subject_type: str = Field(default="sozel")
    is_yks_fen_question: bool = False
    fen_branch: str = ""
    misconception_tag: str = ""
    step_by_step_solution: list[str] = Field(default_factory=list)
    shortcut_tactic: str = ""
    premises: list[PremiseItem] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    video_id: str
    video_url: str
    subject: str | None = None
    cached: bool = Field(
        default=False,
        description="Sonuç önbellekten geldi; LLM isteği harcanmadı",
    )
    notes: list[NoteItem]
    questions: list[QuestionItem]
    teacher_persona: TeacherPersona = Field(default_factory=TeacherPersona)
    job_id: str = ""
    job_status: str = "done"
    job_error: str = ""
    chunks_done: int = 1
    chunks_total: int = 1
    ai_credits_left: int = 0
    ai_credit_limit: int = 7
    is_premium: bool = False
    is_in_trial_period: bool = True
    is_ad_tier: bool = False
    daily_ad_credits: int = 1
    daily_ad_limit: int = 1
    trial_days_left: int = 7


class SavedNoteItem(NoteItem):
    saved_id: int = 0
    subject: str = ""
    video_url: str = ""


class SavedQuestionItem(QuestionItem):
    saved_id: int = 0
    subject: str = ""
    video_url: str = ""
    teacher_persona: TeacherPersona = Field(default_factory=TeacherPersona)


class NotebookSubjectCount(BaseModel):
    name: str
    note_count: int = 0
    question_count: int = 0


class NotebookResponse(BaseModel):
    user_id: str
    subject: str | None = None
    subjects: list[NotebookSubjectCount] = Field(default_factory=list)
    notes: list[SavedNoteItem] = Field(default_factory=list)
    questions: list[SavedQuestionItem] = Field(default_factory=list)


class CompleteTrapRequest(BaseModel):
    user_id: str
    trap_id: int
    chosen: str = Field(..., description="Öğrencinin seçtiği şık (A-E)")


class SaveTrapRequest(BaseModel):
    user_id: str
    question_text: str
    chosen: str = ""
    correct: str = ""
    explanation: str = ""
    trap_explanation: str = ""
    teacher_persona: TeacherPersona | None = None
    topic: str = ""
    question_id: str = ""
    options: dict[str, str] = Field(default_factory=dict)
    time_spent_seconds: int = Field(default=0, ge=0)
    subject_type: str = ""
    shortcut_tactic: str = ""
    step_by_step_solution: list[str] = Field(default_factory=list)
    premises: list[PremiseItem] = Field(default_factory=list)
    misconception_tag: str = ""
    fen_branch: str = ""
    is_yks_fen_question: bool = False


class TrapItem(BaseModel):
    id: int
    user_id: str
    question_id: str = ""
    question_text: str
    options: dict[str, str] = Field(default_factory=dict)
    correct: str = ""
    chosen: str = ""
    explanation: str = ""
    distractor_analysis: str = ""
    teacher_note: str = Field(default="", description="Hoca ağzından kırmızı kalem notu")
    topic: str = ""
    time_spent_seconds: int = 0
    time_trap_triggered: bool = False
    review_count: int = 0
    next_review_date: str | None = None
    subject_type: str = "sozel"
    shortcut_tactic: str = ""
    step_by_step_solution: list[str] = Field(default_factory=list)
    premises: list[PremiseItem] = Field(default_factory=list)
    misconception_tag: str = ""
    fen_branch: str = ""
    is_yks_fen: bool = False


class SaveTrapResponse(BaseModel):
    trap: TrapItem
    time_trap_triggered: bool = False
    warning: str = ""
    new_badges: list[str] = Field(default_factory=list)


class DailyMissionsResponse(BaseModel):
    user_id: str
    due_count: int
    traps: list[TrapItem]


class GameEvent(BaseModel):
    xp_gained: int = 0
    new_badges: list[str] = Field(default_factory=list)
    streak: int = 0
    level: int = 1
    notebook_cleared: bool = False
    title: str = ""
    title_emoji: str = ""
    xp: int = 0


class CompleteTrapResponse(BaseModel):
    trap: TrapItem
    correct: bool
    message: str
    game: GameEvent | None = None


class PrizeSlice(BaseModel):
    monthly_rank: int | None = None
    is_free_next_month: bool = False
    discount_percentage: int = 0
    badge: str | None = None
    tier: str | None = None
    source_month: str | None = None
    projected: bool = False
    correct_count: int = 0
    avg_time_ms: int = 0


class PrizeView(BaseModel):
    live: PrizeSlice = Field(default_factory=PrizeSlice)
    settled: PrizeSlice = Field(default_factory=PrizeSlice)
    badge: str | None = None
    discount_percentage: int = 0
    is_free_next_month: bool = False
    monthly_rank: int | None = None
    total_active_users: int = 0
    prize_stage: str = "launch"
    prize_banner: str = ""


class ProgressResponse(BaseModel):
    user_id: str
    display_name: str
    xp: int
    level: int
    title: str = "Acemi Tilki"
    title_emoji: str = "🦊"
    xp_to_next: int
    current_streak: int
    longest_streak: int
    traps_logged: int
    traps_cleared: int
    badges: list[dict]
    unlocks: list[dict]
    prize: PrizeView = Field(default_factory=PrizeView)
    ai_credits_left: int = 7
    ai_credit_limit: int = 7
    is_premium: bool = False
    is_in_trial_period: bool = True
    is_ad_tier: bool = False
    daily_ad_credits: int = 1
    daily_ad_limit: int = 1
    trial_days_left: int = 7
    is_tested: bool = False
    baseline_score: float = 0
    checkup_due: bool = False
    weak_topics: list[str] = Field(default_factory=list)
    analysis_summary: str = ""
    recommended_videos: list[dict] = Field(default_factory=list)
    exam_target: str = ""
    exam_label: str = ""
    is_onboarded: bool = False
    target_score: float = 85
    target_is_set: bool = False
    current_score: float = 0
    progress_pct: int = 0
    days_until_exam: int = 0
    exam_date: str = ""
    countdown_headline: str = ""
    exam_date_label: str = ""
    today: str = ""
    today_label: str = ""
    subscription_status: str = ""
    subscription_product_id: str = ""
    subscription_expires_at: str | None = None
    role: str = "student"
    teacher_id: str = ""
    teacher_name: str = ""
    dashboard: str = "/"


class LeaderboardResponse(BaseModel):
    entries: list[dict]


class BulletinResponse(BaseModel):
    week_id: str
    title: str
    html_url: str
    created_at: str | None = None
    period_start: str = ""
    period_end: str = ""
    candidate_count: int = 0
    trap_count: int = 0
    traps: list[dict] = Field(default_factory=list)


class DailyCoachResponse(BaseModel):
    user_id: str
    script: str
    audio_url: str | None = None
    trap_count: int = 0


class PenaltyRequest(BaseModel):
    user_id: str
    elapsed_seconds: int = Field(default=0, ge=0)


class ClearPenaltyRequest(BaseModel):
    user_id: str


class PenaltyAnswerRequest(BaseModel):
    user_id: str
    trap_id: int
    chosen: str = Field(..., description="Öğrencinin seçtiği şık (A-E)")


class PenaltyStatus(BaseModel):
    user_id: str
    is_penalized: bool
    penalty_clear_count: int = 0
    needed: int = 3
    trap: TrapItem | None = None
    message: str = ""


class PenaltyAnswerResponse(BaseModel):
    correct: bool
    streak: int
    unlocked: bool
    is_penalized: bool
    needed: int = 3
    trap: TrapItem | None = None
    message: str = ""


class KurnazEntry(BaseModel):
    rank: int
    user_id: str
    display_name: str
    time_spent_ms: int
    title: str
    emoji: str
    badge: str = "pup"
    prize_badge: str | None = None
    monthly_rank: int | None = None


class DailyChallengeStartRequest(BaseModel):
    user_id: str
    challenge_id: int | None = None
    device_id: str = Field(default="", max_length=64)
    identity_hash: str = Field(default="", max_length=128)


class DailyChallengeStartResponse(BaseModel):
    challenge_id: int
    started_at: str | None = None
    already_attempted: bool = False


class DailyChallengeSubmitRequest(BaseModel):
    user_id: str
    chosen: str = Field(..., description="Öğrencinin seçtiği şık (A-E)")
    challenge_id: int | None = None
    device_id: str = Field(default="", max_length=64)
    identity_hash: str = Field(default="", max_length=128)
    time_spent_ms: int = Field(
        default=0,
        ge=0,
        description="Yoksayılır; süre sunucuda started_at ile hesaplanır",
    )


class DailyChallengeSubmitResponse(BaseModel):
    challenge_id: int
    is_correct: bool
    already_attempted: bool = False
    time_spent_ms: int
    trap_explanation: str = ""
    wrong_count: int = 0
    wrong_message: str | None = None
    rank: int | None = None
    leaderboard: list[KurnazEntry] = Field(default_factory=list)
    xp_gained: int = 0
    xp: int = 0
    title: str = ""
    title_emoji: str = ""
    is_suspicious: bool = False
    is_cheated: bool = False
    eligible: bool = False
    suspicious_reason: str | None = None
    subject_type: str = "sozel"
    shortcut_tactic: str = ""
    step_by_step_solution: list[str] = Field(default_factory=list)
    premises: list[PremiseItem] = Field(default_factory=list)
    misconception_tag: str = ""
    fen_branch: str = ""
    is_yks_fen_question: bool = False
    chosen: str = ""


class DailyChallengeItem(BaseModel):
    id: int
    question_text: str
    options: dict[str, str]
    date: str | None = None
    already_attempted: bool = False
    result: DailyChallengeSubmitResponse | None = None
    subject_type: str = "sozel"
    is_yks_fen_question: bool = False
    fen_branch: str = ""
    premises: list[PremiseItem] = Field(default_factory=list)


class DailyChallengeLeaderboardResponse(BaseModel):
    challenge_id: int
    date: str | None = None
    title: str = "Kurnazlar Listesi"
    entries: list[KurnazEntry] = Field(default_factory=list)
    viewer_rank: int | None = None
    total_active_users: int = 0
    prize_stage: str = "launch"
    prize_banner: str = (
        "Kürsü Ödülü: Ay sonunda ilk 3'e girenler sonraki ay BEDAVA Pro kazanıyor!"
    )


class PomodoroCompleteRequest(BaseModel):
    user_id: str
    session_id: str = Field(default="", max_length=64)


class PomodoroCompleteResponse(BaseModel):
    xp_gained: int = 0
    xp: int = 0
    level: int = 1
    title: str = ""
    title_emoji: str = ""
    already: bool = False


class PrizeSettleResponse(BaseModel):
    source_month: str
    already: bool = False
    winner_count: int = 0
    total_active_users: int = 0
    prize_stage: str = "launch"
    prize_banner: str = ""


class AdUnlockRequest(BaseModel):
    user_id: str


class AdUnlockResponse(BaseModel):
    ok: bool = True
    is_ad_tier: bool = False
    daily_ad_credits: int = 1
    daily_ad_limit: int = 1
    is_in_trial_period: bool = False


class DiagnosticAnswer(BaseModel):
    question_id: str
    chosen: str = Field("", max_length=8)


class DiagnosticSubmitRequest(BaseModel):
    user_id: str
    answers: list[DiagnosticAnswer] = Field(default_factory=list)


class DiagnosticQuestion(BaseModel):
    id: str
    topic: str
    question_text: str
    options: dict[str, str]


class DiagnosticExamResponse(BaseModel):
    kind: str
    questions: list[DiagnosticQuestion]


class RecommendedVideo(BaseModel):
    title: str
    topic: str
    url: str


class DiagnosticReport(BaseModel):
    is_tested: bool = True
    score: float
    correct_count: int
    total: int
    weak_topics: list[str] = Field(default_factory=list)
    strong_topics: list[str] = Field(default_factory=list)
    analysis_summary: str = ""
    net_range: str = ""
    topic_breakdown: dict = Field(default_factory=dict)
    recommended_videos: list[RecommendedVideo] = Field(default_factory=list)


class CheckupSubmitResponse(BaseModel):
    score: float
    correct_count: int
    total: int
    weak_topics: list[str] = Field(default_factory=list)
    improvement_summary: str = ""
    score_delta: float | None = None
    previous_score: float | None = None
    checkup_date: str
    topic_breakdown: dict = Field(default_factory=dict)
    recommended_videos: list[RecommendedVideo] = Field(default_factory=list)


class ProgressPoint(BaseModel):
    date: str
    score: float
    weak_topics: list[str] = Field(default_factory=list)
    improvement_summary: str = ""


class ProgressHistoryResponse(BaseModel):
    user_id: str
    points: list[ProgressPoint] = Field(default_factory=list)


class ReportQuestionRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    question_id: str = Field(..., min_length=1, max_length=128)
    reason_text: str = Field(..., min_length=1, max_length=2000)


class ReportQuestionResponse(BaseModel):
    id: int
    question_id: str
    status: str = "pending"
    message: str = ""


class MistakeTypeShare(BaseModel):
    type: str
    count: int = 0
    rate: int = 0


class MistakeDoctorResponse(BaseModel):
    user_id: str
    title: str = ""
    trap_count: int = 0
    types: list[MistakeTypeShare] = Field(default_factory=list)
    dominant: str | None = None
    summary: str = ""
    prescription: str = ""
    weak_topics: list[str] = Field(default_factory=list)
    source: str = "local"


class FeedbackSubmitRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=2000)


class FeedbackSubmitResponse(BaseModel):
    id: int
    category: str
    status: str = "pending"
    message: str = ""


class AdminFeedbackItem(BaseModel):
    id: int
    user_id: str = ""
    display_name: str = ""
    email: str = ""
    phone: str = ""
    category: str = "general"
    category_label: str = ""
    message: str = ""
    status: str = "pending"
    created_at: str | None = None


class AdminFeedbackListResponse(BaseModel):
    items: list[AdminFeedbackItem] = Field(default_factory=list)
    count: int = 0


class AdminFeedbackStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)


class AdminFeedbackStatusResponse(BaseModel):
    id: int
    status: str
    message: str = ""


class SetExamTargetRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    exam_target: str = Field(..., min_length=1, max_length=32)


class SetExamTargetResponse(BaseModel):
    user_id: str
    exam_target: str
    exam_label: str
    is_onboarded: bool = True
    is_tested: bool = False
    reset: bool = False
    title: str = ""
    message: str = ""
    days_left: int = 0
    headline: str = ""
    exam_date: str = ""
    exam_date_label: str = ""
    today: str = ""
    today_label: str = ""


class ExamCountdownResponse(BaseModel):
    exam_target: str
    exam_label: str
    exam_date: str
    exam_date_label: str = ""
    today: str = ""
    today_label: str = ""
    days_left: int = 0
    headline: str = ""


class QuestionBankItem(BaseModel):
    id: str = ""
    topic: str = ""
    question_text: str = ""
    options: dict[str, str] = Field(default_factory=dict)


class QuestionBankResponse(BaseModel):
    exam_target: str
    exam_label: str
    family: str = ""
    subjects: list[str] = Field(default_factory=list)
    questions: list[QuestionBankItem] = Field(default_factory=list)


class SetTargetScoreRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    target_score: float = Field(..., ge=1, le=100)


class SetTargetScoreResponse(BaseModel):
    user_id: str
    target_score: float
    title: str = ""
    message: str = ""


class MotivationalQuoteResponse(BaseModel):
    user_id: str
    quote: str
    title: str = ""
    exam_target: str = ""
    exam_label: str = ""
    date: str = ""


class AuthRequest(BaseModel):
    """Giriş/kayıt: user_id veya email veya telefon + şifre."""

    user_id: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=256)
    phone: str = Field(default="", max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = ""
    display_name: str = Field(default="", max_length=64)
    exam_target: str = Field(default="", max_length=32)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=20, max_length=8192)
    role: str = ""
    display_name: str = Field(default="", max_length=64)
    exam_target: str = Field(default="", max_length=32)
    link_user_id: str = Field(
        default="",
        max_length=128,
        description="Misafir aday-* hesabını Google'a bağlamak için",
    )


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str = "student"
    display_name: str = ""
    dashboard: str = "/"


class ForgotPasswordRequest(BaseModel):
    email: str = Field(default="", max_length=256)
    phone: str = Field(default="", max_length=32)


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    sent: bool = False
    channel: str = "email"
    destination_hint: str = ""
    message: str = ""
    debug_code: str = ""


class ResetPasswordRequest(BaseModel):
    email: str = Field(default="", max_length=256)
    phone: str = Field(default="", max_length=32)
    code: str = Field(..., min_length=4, max_length=12)
    new_password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    ok: bool = True
    user_id: str = ""
    message: str = ""


class AdminSetPasswordRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class AdminSetPasswordResponse(BaseModel):
    ok: bool = True
    user_id: str = ""
    message: str = ""


class AdminUserUpdateRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=32)
    exam_target: str | None = Field(default=None, max_length=32)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserUpdateResponse(BaseModel):
    ok: bool = True
    user_id: str = ""
    display_name: str = ""
    email: str = ""
    phone: str = ""
    exam_target: str = ""
    has_password: bool = False
    message: str = ""


class AdminUserRow(BaseModel):
    user_id: str
    display_name: str = ""
    email: str = ""
    phone: str = ""
    exam_target: str = ""
    role: str = "student"
    is_premium: bool = False
    subscription_status: str = ""
    subscription_expires_at: str | None = None
    ai_credits_left: int = 0
    created_at: str | None = None
    has_google: bool = False
    has_password: bool = False


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRow] = Field(default_factory=list)
    count: int = 0


class AdminGrantProRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    days: int = Field(default=31, ge=1, le=3650)
    revoke: bool = False


class AdminGrantProResponse(BaseModel):
    ok: bool = True
    user_id: str = ""
    is_premium: bool = False
    subscription_status: str = ""
    subscription_expires_at: str | None = None
    message: str = ""


class SubscriptionPlan(BaseModel):
    id: str
    label: str
    period: str = ""
    days: int = 31
    price_try: int = 0
    price_label: str = ""


class SubscriptionVerifyRequest(BaseModel):
    model_config = {"extra": "allow"}
    user_id: str = ""
    product_id: str = Field(default="", max_length=64)
    purchase_token: str = Field(default="", max_length=4096)
    order_id: str = Field(default="", max_length=128)
    platform: str = Field(default="sandbox", max_length=32)


class DynamicExamGenerateRequest(BaseModel):
    user_id: str = ""
    exam_target: str = Field(default="", max_length=32)
    subjects: list[str] = Field(default_factory=list)
    question_count: int = Field(default=10, ge=5, le=25)


class DynamicExamQuestion(BaseModel):
    id: str
    topic: str = ""
    question_text: str
    options: dict[str, str]
    difficulty: str = "orta"
    subject_type: str = "sozel"
    is_yks_fen_question: bool = False
    fen_branch: str = ""
    premises: list[PremiseItem] = Field(default_factory=list)


class DynamicExamGenerateResponse(BaseModel):
    exam_id: int
    status: str = "pending"
    exam_target: str = ""
    exam_label: str = ""
    subjects: list[str] = Field(default_factory=list)
    question_count: int = 0
    duration_seconds: int = 0
    remaining_seconds: int = 0
    started_at: str | None = None
    questions: list[DynamicExamQuestion] = Field(default_factory=list)
    trap_blend: bool = True
    osym_dna: bool = True
    report: dict | None = None


class DynamicExamCatalogResponse(BaseModel):
    user_id: str = ""
    exam_target: str = ""
    exam_label: str = ""
    family: str = ""
    subjects: list[str] = Field(default_factory=list)
    question_counts: list[int] = Field(default_factory=list)
    seconds_per_question: int = 75


class DynamicExamAnswer(BaseModel):
    question_id: str
    chosen: str = Field(default="", max_length=8)


class DynamicExamSubmitRequest(BaseModel):
    user_id: str = ""
    exam_id: int
    answers: list[DynamicExamAnswer]
    time_spent_seconds: int | None = None


class DynamicExamReview(BaseModel):
    question_id: str = ""
    topic: str = ""
    question_text: str = ""
    options: dict[str, str] = Field(default_factory=dict)
    chosen: str = ""
    correct: str = ""
    is_correct: bool = False
    explanation: str = ""
    trap_explanation: str = ""
    subject_type: str = "sozel"
    is_yks_fen_question: bool = False
    fen_branch: str = ""
    misconception_tag: str = ""
    step_by_step_solution: list[str] = Field(default_factory=list)
    shortcut_tactic: str = ""
    premises: list[PremiseItem] = Field(default_factory=list)


class DynamicExamReport(BaseModel):
    exam_id: int
    already: bool = False
    score: float = 0.0
    correct_count: int = 0
    total: int = 0
    weak_topics: list[str] = Field(default_factory=list)
    strong_topics: list[str] = Field(default_factory=list)
    topic_breakdown: dict = Field(default_factory=dict)
    net_range: str = ""
    coach_summary: str = ""
    weakness_analysis: str = ""
    prescription: str = ""
    traps_hit: list[str] = Field(default_factory=list)
    reviews: list[DynamicExamReview] = Field(default_factory=list)
    recommended_videos: list[RecommendedVideo] = Field(default_factory=list)
    is_cheated: bool = False
    traps_saved: int = 0
    time_spent_seconds: int = 0
    exam_target: str = ""
    exam_label: str = ""
    subjects: list[str] = Field(default_factory=list)
    xp_gained: int = 0
    xp: int = 0
    level: int = 0
    title: str = ""
    title_emoji: str = ""


class SubscriptionStatusResponse(BaseModel):
    ok: bool = True
    is_premium: bool = False
    subscription_status: str = "none"
    product_id: str = ""
    expires_at: str | None = None
    sandbox: bool = True
    package_name: str = ""
    plans: list[SubscriptionPlan] = Field(default_factory=list)
    message: str = ""


class AdminCreditsGrantRequest(BaseModel):
    user_id: str = Field(default="", max_length=128)
    credits: int | None = Field(default=None, ge=0, le=35)
    premium: bool | None = None


class AdminCreditsGrantResponse(BaseModel):
    ok: bool = True
    user_id: str = ""
    ai_credits_left: int = 7
    ai_credit_limit: int = 7
    is_premium: bool = False
    is_in_trial_period: bool = True
    message: str = ""


class PromoCreateRequest(BaseModel):
    code: str = Field(default="", max_length=32)
    discount_type: str = Field(default="percentage", max_length=16)
    value: float = Field(default=20)
    max_uses: int = Field(default=0, ge=0, le=100000)
    quantity: int = Field(default=1, ge=1, le=500)
    expires_at: str | None = None
    created_by_teacher_id: str = Field(default="", max_length=128)
    enroll_to_class: bool = False


class PromoApplyRequest(BaseModel):
    user_id: str = ""
    code: str = Field(default="", max_length=32)
    product_id: str = Field(default="tilko_pro_monthly", max_length=64)


class PromoRedemptionView(BaseModel):
    user_id: str
    product_id: str = ""
    original_price: float = 0
    discount_amount: float = 0
    payable_amount: float = 0
    used_at: str | None = None


class PromoCodeView(BaseModel):
    id: int = 0
    code: str
    discount_type: str
    value: float
    max_uses: int = 0
    used_count: int = 0
    remaining: int | None = None
    used_by: list[str] = Field(default_factory=list)
    created_by_teacher_id: str = ""
    enroll_to_class: bool = False
    expires_at: str | None = None
    created_at: str | None = None
    status: str = "active"
    redemptions: list[PromoRedemptionView] = Field(default_factory=list)


class PromoCreateResponse(BaseModel):
    ok: bool = True
    count: int = 1
    coupons: list[PromoCodeView] = Field(default_factory=list)
    message: str = ""


class PromoListResponse(BaseModel):
    coupons: list[PromoCodeView] = Field(default_factory=list)
    count: int = 0


class PromoApplyResponse(BaseModel):
    ok: bool = True
    code: str
    discount_type: str
    value: float
    product_id: str = ""
    original_price: float
    discount_amount: float
    payable_amount: float
    message: str = ""
    status: str = "active"
    used_count: int = 0
    max_uses: int = 0
    classroom_joined: bool = False
    teacher_id: str = ""
    teacher_name: str = ""
    join_message: str = ""


class TeacherStudentCard(BaseModel):
    user_id: str
    display_name: str = ""
    baseline_score: float = 0
    net_range: str = ""
    is_tested: bool = False
    trap_count: int = 0
    traps_cleared: int = 0
    xp: int = 0
    weak_topics: list[str] = Field(default_factory=list)
    exam_target: str = ""
    analysis_summary: str = ""
    rank: int = 0


class TeacherHotTopic(BaseModel):
    topic: str
    hits: int = 0
    intensity: int = 0


class TeacherClassroomResponse(BaseModel):
    teacher_id: str
    teacher_name: str = ""
    role: str = "teacher"
    student_count: int = 0
    class_average: float = 0
    students: list[TeacherStudentCard] = Field(default_factory=list)
    ranking: list[TeacherStudentCard] = Field(default_factory=list)
    hot_topics: list[TeacherHotTopic] = Field(default_factory=list)


class TeacherStudentAnalysisResponse(BaseModel):
    student: TeacherStudentCard
    doctor: MistakeDoctorResponse
    traps: list[TrapItem] = Field(default_factory=list)
    baseline: dict = Field(default_factory=dict)
    weak_topics: list[str] = Field(default_factory=list)
    analysis_summary: str = ""


class TeacherShareRequest(BaseModel):
    title: str = "Sazan Avı"
    topic: str = ""
    question_text: str = Field(..., min_length=8)
    options: dict[str, str] = Field(default_factory=dict)
    correct: str = ""
    explanation: str = ""
    student_ids: list[str] = Field(default_factory=list)


class TeacherAssignmentView(BaseModel):
    id: int = 0
    teacher_id: str = ""
    title: str = ""
    topic: str = ""
    question_text: str = ""
    options: dict[str, str] = Field(default_factory=dict)
    correct: str = ""
    explanation: str = ""
    assigned_count: int = 0
    completed_count: int = 0
    assigned_to: list[str] = Field(default_factory=list)
    created_at: str | None = None
    completed: bool = False


class TeacherAssignmentListResponse(BaseModel):
    assignments: list[TeacherAssignmentView] = Field(default_factory=list)
    count: int = 0
    teacher_id: str = ""
    teacher_name: str = ""


class TeacherAssignmentSubmitRequest(BaseModel):
    user_id: str = ""
    assignment_id: int
    chosen: str = ""


class TeacherAssignmentSubmitResponse(BaseModel):
    ok: bool = True
    correct: bool = False
    message: str = ""
    answer: str = ""
    explanation: str = ""


class ExamScheduleItem(BaseModel):
    exam_target: str
    label: str = ""
    exam_date: str
    exam_date_label: str = ""
    days_remaining: int = 0
    message: str = ""


class ExamScheduleListResponse(BaseModel):
    exams: list[ExamScheduleItem] = Field(default_factory=list)
    count: int = 0
    today: str = ""
    today_label: str = ""
    today_override: bool = False
    real_today: str = ""
    real_today_label: str = ""
    message: str = ""


class ExamScheduleUpdateRequest(BaseModel):
    exam_target: str = Field(..., min_length=2, max_length=32)
    exam_date: str = Field(..., min_length=8, max_length=40)


class ExamClockUpdateRequest(BaseModel):
    exam_date: str = ""
    reset: bool = False
