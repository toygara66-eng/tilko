from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrapNotebook(Base):
    """Yanlış veya süre tuzağına düşülen sorular — Ebbinghaus tekrar defteri."""

    __tablename__ = "trap_notebook"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    question_id: Mapped[str] = mapped_column(String(64), default="")
    question_text: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    correct: Mapped[str] = mapped_column(String(8), default="")
    chosen: Mapped[str] = mapped_column(String(8), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    distractor_analysis: Mapped[str] = mapped_column(Text, default="")
    teacher_note: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(128), default="")
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    time_trap_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    subject_type: Mapped[str] = mapped_column(String(16), default="sozel")
    shortcut_tactic: Mapped[str] = mapped_column(Text, default="")
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    premises_json: Mapped[str] = mapped_column(Text, default="[]")
    misconception_tag: Mapped[str] = mapped_column(String(64), default="")
    fen_branch: Mapped[str] = mapped_column(String(32), default="")
    is_yks_fen: Mapped[bool] = mapped_column(Boolean, default=False)
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    next_review_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class UserStats(Base):
    """Oyunlaştırma: XP, seri, tuzak avı sayaçları."""

    __tablename__ = "user_stats"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_streak_date: Mapped[str] = mapped_column(String(16), default="")
    traps_logged: Mapped[int] = mapped_column(Integer, default=0)
    traps_cleared: Mapped[int] = mapped_column(Integer, default=0)
    last_pomodoro_session: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class User(Base):
    """Odak cezası: Pomodoro ihlali ve kilit açma serisi."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_penalized: Mapped[bool] = mapped_column(Boolean, default=False)
    penalty_clear_count: Mapped[int] = mapped_column(Integer, default=0)
    discount_percentage: Mapped[int] = mapped_column(Integer, default=0)
    is_free_next_month: Mapped[bool] = mapped_column(Boolean, default=False)
    prize_rank: Mapped[int] = mapped_column(Integer, default=0)
    prize_source_month: Mapped[str] = mapped_column(String(7), default="")
    identity_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_credits_left: Mapped[int] = mapped_column(Integer, default=7)
    baseline_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_tested: Mapped[bool] = mapped_column(Boolean, default=False)
    exam_target: Mapped[str] = mapped_column(String(32), default="")
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    target_score: Mapped[float] = mapped_column(Float, default=0.0)
    password_hash: Mapped[str] = mapped_column(String(256), default="")
    google_sub: Mapped[str] = mapped_column(String(64), default="", index=True)
    email: Mapped[str] = mapped_column(String(256), default="", index=True)
    phone: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    daily_ad_rewarded_credits: Mapped[int] = mapped_column(Integer, default=1)
    last_credit_reset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_ad_unlock_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_product_id: Mapped[str] = mapped_column(String(64), default="")
    subscription_status: Mapped[str] = mapped_column(String(32), default="")
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    play_purchase_token_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    role: Mapped[str] = mapped_column(String(16), default="student", index=True)
    teacher_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    display_name: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ProEntitlementEvent(Base):
    """Pro aç/kapa/bitiş denetim kaydı — ödeme itirazı için."""

    __tablename__ = "pro_entitlement_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(32), default="", index=True)
    source: Mapped[str] = mapped_column(String(32), default="", index=True)
    days: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(String(512), default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DiagnosticTest(Base):
    """İlk seviye teşhisi — konu bazlı doğru/yanlış kaydı."""

    __tablename__ = "diagnostic_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    weak_topics: Mapped[str] = mapped_column(Text, default="[]")
    strong_topics: Mapped[str] = mapped_column(Text, default="[]")
    analysis_summary: Mapped[str] = mapped_column(Text, default="")
    net_range: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserBaseline(Base):
    """Kullanıcının güncel seviye özeti — zayıf konular ve rota."""

    __tablename__ = "user_baselines"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    weak_topics: Mapped[str] = mapped_column(Text, default="[]")
    strong_topics: Mapped[str] = mapped_column(Text, default="[]")
    analysis_summary: Mapped[str] = mapped_column(Text, default="")
    net_range: Mapped[str] = mapped_column(String(32), default="")
    topic_breakdown: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class DiagnosticIpMark(Base):
    """Aynı IP'de seviye teşhisi bir kez geçildi; misafir oturum tekrar sormaz."""

    __tablename__ = "diagnostic_ip_marks"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_user_id: Mapped[str] = mapped_column(String(128), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OnboardingIpMark(Base):
    """Aynı IP'de sınav hedefi bir kez seçildi; misafir oturum /hedef'i tekrar açmaz."""

    __tablename__ = "onboarding_ip_marks"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_user_id: Mapped[str] = mapped_column(String(128), index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="")
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProgressCheckup(Base):
    """Haftalık/aylık gelişim check-up kaydı."""

    __tablename__ = "progress_checkups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    checkup_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    weak_topics: Mapped[str] = mapped_column(Text, default="[]")
    improvement_summary: Mapped[str] = mapped_column(Text, default="")
    topic_breakdown: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DynamicExam(Base):
    """Kişiselleştirilmiş anlık deneme — ÖSYM DNA + Tuzak Defteri."""

    __tablename__ = "dynamic_exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    subjects_json: Mapped[str] = mapped_column(Text, default="[]")
    question_count: Mapped[int] = mapped_column(Integer, default=10)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=750)
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    answers_json: Mapped[str] = mapped_column(Text, default="[]")
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    is_cheated: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AiConversion(Base):
    """Ücretsiz denemede video başına tek kredi — tekrar izleme kotayı yemez."""

    __tablename__ = "ai_conversions"
    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_ai_conversion_user_video"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    video_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    badge_id: Mapped[str] = mapped_column(String(64))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WeeklyBulletin(Base):
    __tablename__ = "weekly_bulletins"

    week_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    html_path: Mapped[str] = mapped_column(String(512), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DailyChallenge(Base):
    """Günün Sazan Avı — takvim günü + sınav hedefi."""

    __tablename__ = "daily_challenges"
    __table_args__ = (UniqueConstraint("date", "exam_target", name="uq_daily_exam"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_text: Mapped[str] = mapped_column(Text)
    options: Mapped[str] = mapped_column(Text, default="{}")
    correct_answer: Mapped[str] = mapped_column(String(8), default="")
    trap_explanation: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[date] = mapped_column(Date, index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="kpss_lisans", index=True)
    subject_type: Mapped[str] = mapped_column(String(16), default="sozel")
    shortcut_tactic: Mapped[str] = mapped_column(Text, default="")
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    premises_json: Mapped[str] = mapped_column(Text, default="[]")
    misconception_tag: Mapped[str] = mapped_column(String(64), default="")
    fen_branch: Mapped[str] = mapped_column(String(32), default="")
    is_yks_fen: Mapped[bool] = mapped_column(Boolean, default=False)


class ChallengeLeaderboard(Base):
    """Kurnazlar Listesi — günün avını milisaniye hızıyla çözenler."""

    __tablename__ = "challenge_leaderboard"
    __table_args__ = (
        UniqueConstraint("user_id", "challenge_id", name="uq_challenge_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, index=True)
    time_spent_ms: Mapped[int] = mapped_column(Integer, default=0)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cheated: Mapped[bool] = mapped_column(Boolean, default=False)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChallengeSession(Base):
    """Sazan Avı açılış anı — süre yalnızca sunucuda başlar."""

    __tablename__ = "challenge_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "challenge_id", name="uq_challenge_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    challenge_id: Mapped[int] = mapped_column(Integer, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    device_id: Mapped[str] = mapped_column(String(64), default="")
    ip_hash: Mapped[str] = mapped_column(String(64), default="")


class DeviceSighting(Base):
    """Hesap-cihaz-IP bağları — yan hesap kümeleme."""

    __tablename__ = "device_sightings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    device_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PrizeGrant(Base):
    """Kimlik/cihaz başına ömür boyu tek indirim kaydı."""

    __tablename__ = "prize_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    source_month: Mapped[str] = mapped_column(String(7), default="")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MonthlyPrizeRun(Base):
    """Hangi ayın Sazan Avı sıralamasının ödüle bağlandığı."""

    __tablename__ = "monthly_prize_runs"

    source_month: Mapped[str] = mapped_column(String(7), primary_key=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    winner_count: Mapped[int] = mapped_column(Integer, default=0)


class ReportedQuestion(Base):
    """Kullanıcının hatalı gördüğü Sazan Avı / test sorusu bildirimi."""

    __tablename__ = "reported_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    reason_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserFeedback(Base):
    """Platform geliştirme önerileri."""

    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(32), default="general", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PasswordReset(Base):
    """Şifre sıfırlama kodu (e-posta / telefon)."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), default="")
    channel: Mapped[str] = mapped_column(String(16), default="email")
    destination: Mapped[str] = mapped_column(String(256), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PlayPurchase(Base):
    """Google Play / sandbox abonelik fişi — token tekrarını engeller."""

    __tablename__ = "play_purchases"
    __table_args__ = (UniqueConstraint("purchase_token_hash", name="uq_play_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    product_id: Mapped[str] = mapped_column(String(64), default="")
    purchase_token_hash: Mapped[str] = mapped_column(String(64), default="")
    order_id: Mapped[str] = mapped_column(String(128), default="")
    platform: Mapped[str] = mapped_column(String(32), default="sandbox")
    status: Mapped[str] = mapped_column(String(32), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class OsymArchiveDoc(Base):
    """Yüklenen ÖSYM arşiv dosyası — son 10 yıl soru metni / analizi."""

    __tablename__ = "osym_archive_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    exam_year: Mapped[int] = mapped_column(Integer, default=0, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    text_excerpt: Mapped[str] = mapped_column(Text, default="")
    patterns_json: Mapped[str] = mapped_column(Text, default="{}")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OsymArchiveChunk(Base):
    """RAG parçası: soru kökü, tuzak, konu."""

    __tablename__ = "osym_archive_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    kind: Mapped[str] = mapped_column(String(32), default="stem")
    body: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(128), default="", index=True)
    exam_year: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OsymStyleGuide(Base):
    """Sınav bazlı ÖSYM kalıp özeti — soru üretim parametreleri."""

    __tablename__ = "osym_style_guide"

    exam_target: Mapped[str] = mapped_column(String(32), primary_key=True)
    years: Mapped[str] = mapped_column(String(32), default="")
    stems_json: Mapped[str] = mapped_column(Text, default="[]")
    traps_json: Mapped[str] = mapped_column(Text, default="[]")
    topics_json: Mapped[str] = mapped_column(Text, default="[]")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class HocaHighlight(Base):
    """Videodaki hoca vurgusu — banko / dikkat edin sinyalı."""

    __tablename__ = "hoca_highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    video_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    subject: Mapped[str] = mapped_column(String(128), default="")
    cue: Mapped[str] = mapped_column(String(64), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(128), default="", index=True)
    timestamp: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TopicSignal(Base):
    """Soru havuzu için önemli konu sinyali (vurgu + arşiv)."""

    __tablename__ = "topic_signals"
    __table_args__ = (UniqueConstraint("exam_target", "topic", name="uq_topic_signal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="", index=True)
    topic: Mapped[str] = mapped_column(String(128), default="")
    weight: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="highlight")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TokenUsageLog(Base):
    """OpenRouter sohbet çağrılarının jeton kullanımı."""

    __tablename__ = "token_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), default="", index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    task: Mapped[str] = mapped_column(String(64), default="genel", index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class PromoCode(Base):
    """Tek veya çok kullanımlık indirim kuponu."""

    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    discount_type: Mapped[str] = mapped_column(String(16), default="percentage")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    used_by_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_by_teacher_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    enroll_to_class: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PromoRedemption(Base):
    """Kuponu kim, ne zaman, hangi plana uyguladı."""

    __tablename__ = "promo_redemptions"
    __table_args__ = (
        UniqueConstraint("promo_id", "user_id", name="uq_promo_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(32), default="", index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    product_id: Mapped[str] = mapped_column(String(64), default="")
    original_price: Mapped[float] = mapped_column(Float, default=0.0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0)
    payable_amount: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class TeacherStudent(Base):
    """Hoca-öğrenci sınıf bağısı — kupon veya manuel eşleşme."""

    __tablename__ = "teacher_students"
    __table_args__ = (
        UniqueConstraint("teacher_id", "student_id", name="uq_teacher_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[str] = mapped_column(String(128), index=True)
    student_id: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(16), default="promo")
    promo_code: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class TeacherAssignment(Base):
    """Hocanın sınıfa attığı Sazan Avı / özel soru seti."""

    __tablename__ = "teacher_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(128), default="Sazan Avı")
    topic: Mapped[str] = mapped_column(String(128), default="")
    question_text: Mapped[str] = mapped_column(Text, default="")
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    correct: Mapped[str] = mapped_column(String(8), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    assigned_to_json: Mapped[str] = mapped_column(Text, default="[]")
    completed_by_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class ExamSchedule(Base):
    """Merkezi sınav takvimi — geri sayım bu tablodan okunur."""

    __tablename__ = "exam_schedules"

    exam_target: Mapped[str] = mapped_column(String(32), primary_key=True)
    exam_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SavedNotebookItem(Base):
    """Analizden biriken ders notu veya soru — kaybolmaz."""

    __tablename__ = "saved_notebook"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint", name="uq_saved_notebook_fp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    subject: Mapped[str] = mapped_column(String(64), default="", index=True)
    video_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    video_url: Mapped[str] = mapped_column(String(256), default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    timestamp: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NotebookSession(Base):
    """Kullanıcının bir video not setine verdiği özel isim (ders klasörü altında)."""

    __tablename__ = "notebook_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "subject", "video_id", name="uq_notebook_session_user_subj_vid"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    subject: Mapped[str] = mapped_column(String(64), default="", index=True)
    video_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    video_url: Mapped[str] = mapped_column(String(256), default="")
    label: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AnalyzeCache(Base):
    """Aynı YouTube videosu için paylaşılan analiz sonucu — LLM tekrar çağrılmaz."""

    __tablename__ = "analyze_cache"
    __table_args__ = (
        UniqueConstraint("lookup_key", name="uq_analyze_cache_lookup"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lookup_key: Mapped[str] = mapped_column(String(320), default="", index=True)
    video_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    subject: Mapped[str] = mapped_column(String(64), default="", index=True)
    exam_target: Mapped[str] = mapped_column(String(32), default="")
    focus_bucket: Mapped[int] = mapped_column(Integer, default=0)
    llm_model: Mapped[str] = mapped_column(String(128), default="")
    notes_depth: Mapped[int] = mapped_column(Integer, default=0)
    note_count: Mapped[int] = mapped_column(Integer, default=0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
