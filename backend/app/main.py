import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import get_db, init_db
from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BulletinResponse,
    ClearPenaltyRequest,
    CompleteTrapRequest,
    CompleteTrapResponse,
    DailyMissionsResponse,
    GameEvent,
    LeaderboardResponse,
    NoteItem,
    NotebookResponse,
    PenaltyAnswerRequest,
    PenaltyAnswerResponse,
    PenaltyRequest,
    PenaltyStatus,
    ProgressResponse,
    QuestionItem,
    SaveTrapRequest,
    SaveTrapResponse,
    TrapItem,
    DailyChallengeItem,
    DailyChallengeLeaderboardResponse,
    DailyChallengeStartRequest,
    DailyChallengeStartResponse,
    DailyChallengeSubmitRequest,
    DailyChallengeSubmitResponse,
    PomodoroCompleteRequest,
    PomodoroCompleteResponse,
    PrizeSettleResponse,
    PrizeView,
    AdUnlockRequest,
    AdUnlockResponse,
    DiagnosticExamResponse,
    DiagnosticReport,
    DiagnosticSubmitRequest,
    CheckupSubmitResponse,
    ProgressHistoryResponse,
    ReportQuestionRequest,
    ReportQuestionResponse,
    MistakeDoctorResponse,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
    AdminFeedbackListResponse,
    AdminFeedbackItem,
    AdminFeedbackStatusRequest,
    AdminFeedbackStatusResponse,
    SetExamTargetRequest,
    SetExamTargetResponse,
    ExamCountdownResponse,
    QuestionBankResponse,
    SetTargetScoreRequest,
    SetTargetScoreResponse,
    MotivationalQuoteResponse,
    AuthRequest,
    AuthResponse,
    GoogleAuthRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    AdminSetPasswordRequest,
    AdminSetPasswordResponse,
    AdminUserUpdateRequest,
    AdminUserUpdateResponse,
    AdminUserListResponse,
    AdminUserRow,
    AdminGrantProRequest,
    AdminGrantProResponse,
    SubscriptionVerifyRequest,
    SubscriptionStatusResponse,
    PromoCreateRequest,
    PromoCreateResponse,
    PromoCodeView,
    PromoListResponse,
    PromoApplyRequest,
    PromoApplyResponse,
    TeacherClassroomResponse,
    TeacherStudentAnalysisResponse,
    TeacherShareRequest,
    TeacherAssignmentView,
    TeacherAssignmentListResponse,
    TeacherAssignmentSubmitRequest,
    TeacherAssignmentSubmitResponse,
    ExamScheduleListResponse,
    ExamScheduleUpdateRequest,
    ExamClockUpdateRequest,
    ExamScheduleItem,
    DynamicExamGenerateRequest,
    DynamicExamGenerateResponse,
    DynamicExamCatalogResponse,
    DynamicExamSubmitRequest,
    DynamicExamReport,
    AdminCreditsGrantRequest,
    AdminCreditsGrantResponse,
)
from app.services import ai_engine
from app.services import bulletin as bulletin_service
from app.services import cache
from app.services import anti_cheat
from app.services import daily_challenge as hunt_service
from app.services import gamification
from app.services import penalty as penalty_service
from app.services import prizes as prize_service
from app.services import traps as trap_service
from app.services import notebook as notebook_service
from app.services import credits as credit_service
from app.services import diagnostic as diagnostic_service
from app.services import dynamic_exam as dynamic_exam_service
from app.services import reports as report_service
from app.services import mistake_doctor as doctor_service
from app.services import feedback as feedback_service
from app.services.credits import (
    AdQuotaExceededError,
    AdRequiredError,
    QuotaExceededError as CreditQuotaExceededError,
    VideoTooLongError,
)
from app.services.llm import (
    ConfigurationError,
    QuotaExhaustedError,
    analyze_slice,
    quick_transcript_notes,
    require_analyze_llm,
)
from app.services.scale import (
    ServiceBusyError,
    claim_work,
    release_work,
)
from app.security.auth import (
    actor,
    admin_ok,
    jwt_guard,
    login_user,
    login_with_google,
    play_webhook_ok,
    register_user,
)
from app.security.rate_limit import limiter
from app.services.youtube import (
    YOUTUBE_ID_RE,
    build_watch_url,
    extract_start_seconds,
    extract_video_id,
    fetch_transcript_lines,
    focus_bucket as youtube_focus_bucket,
    format_timestamp_label,
    normalize_transcript_lines,
    pick_content_slice,
    slice_transcript,
    transcript_duration_seconds,
    transcript_off_subject,
)

WEB_DIR = Path(__file__).parent / "web"
logger = logging.getLogger(__name__)
SLICE_SECONDS = 300


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.is_production and (
        not (settings.jwt_secret or "").strip()
        or settings.jwt_secret.strip() in {"tilko-dev-jwt-change-me", "change-me", "secret"}
        or len(settings.jwt_secret.strip()) < 32
    ):
        raise RuntimeError(
            "Üretimde JWT_SECRET ortam değişkeni zorunlu (en az 32 karakter, varsayılan yasak)."
        )
    init_db()
    yield


app = FastAPI(
    title="TİLKO API",
    description="YouTube altyazısından saniye damgalı not ve ÖSYM tarzı soru üretir.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.middleware("http")(jwt_guard)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    from app.services.llm import analyze_llm_ready

    llm = analyze_llm_ready()
    cache_videos = 0
    try:
        from app.database.models import AnalyzeCache
        from app.database.session import SessionLocal

        db = SessionLocal()
        try:
            cache_videos = int(db.query(AnalyzeCache).count() or 0)
        finally:
            db.close()
    except Exception:
        cache_videos = 0
    body = {
        "status": "ok" if (not settings.is_production or llm["ready"]) else "degraded",
        "llm_ready": bool(llm["ready"]),
        "provider": str(llm.get("provider") or settings.llm_provider),
        "model": str(llm.get("model") or settings.active_model),
        "gemini": bool(llm.get("gemini")),
        "nebius": bool(llm.get("nebius")),
        "groq": bool(llm["groq"]),
        "cerebras": bool(llm["cerebras"]),
        "analyze_cache_videos": cache_videos,
    }
    return body


@app.get("/captions/{video_id}")
@limiter.limit("12/minute")
def captions_lookup(request: Request, video_id: str) -> dict:
    if not YOUTUBE_ID_RE.match(video_id or ""):
        raise HTTPException(status_code=400, detail="Geçerli bir YouTube video kimliği bulunamadı.")
    try:
        lines = fetch_transcript_lines(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"video_id": video_id, "lines": lines}


@app.post("/auth/register", response_model=AuthResponse)
@limiter.limit("20/minute")
def auth_register(
    request: Request, payload: AuthRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    try:
        data = register_user(
            db,
            payload.user_id,
            payload.password,
            role=payload.role,
            display_name=payload.display_name,
            email=payload.email,
            phone=payload.phone,
            exam_target=payload.exam_target,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthResponse.model_validate(data)


@app.post("/auth/login", response_model=AuthResponse)
@app.post("/login", response_model=AuthResponse)
@limiter.limit("40/minute")
def auth_login(
    request: Request, payload: AuthRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    try:
        data = login_user(
            db,
            payload.user_id,
            payload.password,
            role=payload.role,
            display_name=payload.display_name,
            email=payload.email,
            phone=payload.phone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse.model_validate(data)


@app.post("/auth/google", response_model=AuthResponse)
@limiter.limit("30/minute")
def auth_google(
    request: Request, payload: GoogleAuthRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    try:
        data = login_with_google(
            db,
            payload.id_token,
            role=payload.role,
            display_name=payload.display_name,
            exam_target=payload.exam_target,
            link_user_id=payload.link_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse.model_validate(data)


@app.post("/auth/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit("8/minute")
def auth_forgot_password(
    request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)
) -> ForgotPasswordResponse:
    from app.services import password_reset as reset_service

    try:
        data = reset_service.request_password_reset(
            db, email=payload.email, phone=payload.phone
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ForgotPasswordResponse.model_validate(data)


@app.post("/auth/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("8/minute")
def auth_reset_password(
    request: Request, payload: ResetPasswordRequest, db: Session = Depends(get_db)
) -> ResetPasswordResponse:
    from app.services import password_reset as reset_service

    try:
        data = reset_service.reset_password_with_code(
            db,
            email=payload.email,
            phone=payload.phone,
            code=payload.code,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResetPasswordResponse.model_validate(data)


def _busy_http(exc: BaseException) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=str(exc) or "Sunucu meşgul. 15 saniye sonra tekrar dene.",
        headers={"Retry-After": "15"},
    )


def _deliver_cached_analyze(
    *,
    cached: dict,
    db: Session,
    user_id: str,
    video_id: str,
    subject: str | None,
    reservation,
    exam_target: str | None,
) -> AnalyzeResponse:
    reservation = credit_service.confirm(db, user_id, video_id, reservation)
    extra = {
        "cached": True,
        "job_id": "",
        "job_status": "done",
        "chunks_done": 1,
        "chunks_total": 1,
        **credit_service.overlay(reservation),
    }
    response = AnalyzeResponse.model_validate({**cached, **extra})
    _persist_notebook(
        user_id=user_id,
        subject=subject,
        video_id=video_id,
        video_url=response.video_url,
        notes=response.notes,
        questions=response.questions,
        persona=response.teacher_persona,
        exam_target=exam_target,
        db=db,
    )
    return response


def _deliver_shared_job(
    job: dict,
    reservation,
    *,
    user_id: str,
    subject: str | None,
    exam_target: str | None,
) -> AnalyzeResponse:
    overlay = credit_service.overlay(reservation)
    notes = job.get("notes") or []
    questions = job.get("questions") or []
    persona = job.get("teacher_persona") or {"catchphrases": [], "tone": "öğretici, net"}
    if notes or questions:
        _persist_notebook(
            user_id=user_id,
            subject=subject or job.get("subject"),
            video_id=job["video_id"],
            video_url=job["video_url"],
            notes=notes,
            questions=questions,
            persona=persona,
            exam_target=exam_target,
        )
    return AnalyzeResponse(
        video_id=job["video_id"],
        video_url=job["video_url"],
        subject=job.get("subject") or None,
        notes=notes,
        questions=questions,
        teacher_persona=persona,
        job_id=job["id"],
        job_status=job.get("status") or "running",
        job_error=job.get("error") or "",
        chunks_done=int(job.get("chunks_done") or 0),
        chunks_total=int(job.get("chunks_total") or 1),
        cached=False,
        **overlay,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
@app.post("/convert-video", response_model=AnalyzeResponse)
@limiter.limit("8/minute")
def analyze_video(
    request: Request,
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    video_url = str(payload.video_url)
    user_id = (payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Kullanıcı kimliği gerekli.")
    try:
        video_id = extract_video_id(video_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    focus_start = extract_start_seconds(video_url)
    focus_bkt = youtube_focus_bucket(focus_start, SLICE_SECONDS)
    try:
        require_analyze_llm()
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    lines = normalize_transcript_lines(
        [item.model_dump() for item in payload.transcript_lines]
        if payload.transcript_lines
        else None
    )
    user = penalty_service.get_or_create_user(db, user_id)
    from app.services.exams import exam_of

    exam_target = exam_of(db, user_id)
    credit_service.reset_daily_ads(db, user)
    free_admin = admin_ok(request)
    if (
        not free_admin
        and credit_service.is_ad_tier(user)
        and not credit_service.already_converted(db, user_id, video_id)
    ):
        if not payload.ad_watched and not credit_service.ad_unlocked(user):
            raise HTTPException(
                status_code=403,
                detail=str(AdRequiredError(title=gamification.address_for(db, user_id))),
            )
        if lines:
            try:
                credit_service.enforce_duration(
                    user, transcript_duration_seconds(lines), db
                )
            except VideoTooLongError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        reservation = (
            credit_service.admin_bypass(db, user_id)
            if free_admin
            else credit_service.reserve(
                db,
                user_id,
                video_id,
                ad_watched=bool(payload.ad_watched),
            )
        )
    except CreditQuotaExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except AdQuotaExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except AdRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    extra_keys = (
        "ai_credits_left",
        "ai_credit_limit",
        "is_premium",
        "is_in_trial_period",
        "is_ad_tier",
        "daily_ad_credits",
        "daily_ad_limit",
        "trial_days_left",
    )
    from app.services.subjects import classify
    from app.services import rag as rag_service

    subject_meta = classify(
        subject=payload.subject,
        subject_type=payload.subject_type,
        exam_target=exam_target,
        is_yks_fen_question=payload.is_yks_fen_question,
    )
    cache_key = cache.build_key(
        video_id,
        payload.subject,
        payload.question_count,
        exam_target,
        subject_meta["subject_type"],
        subject_meta["is_yks_fen_question"],
        rag_service.style_revision(db, exam_target),
        focus_bucket=focus_bkt,
    )
    cached = cache.load(cache_key) or cache.find_cached(
        video_id, payload.subject, exam_target, focus_bucket=focus_bkt
    )
    if cached:
        return _deliver_cached_analyze(
            cached=cached,
            db=db,
            user_id=user_id,
            video_id=video_id,
            subject=payload.subject,
            reservation=reservation,
            exam_target=exam_target,
        )

    canonical_url = build_watch_url(
        video_id, focus_start if focus_start > 0 else None
    )
    overlay = credit_service.overlay(reservation)
    from app.services import analyze_jobs as jobs

    shared = jobs.find_running(video_id, payload.subject, focus_bucket=focus_bkt)
    if shared:
        status = shared.get("status") or "running"
        notes = shared.get("notes") or []
        questions = shared.get("questions") or []
        if status == "error":
            credit_service.refund(db, user_id, reservation)
            raise HTTPException(
                status_code=502,
                detail=shared.get("error") or "Paylaşılan analiz başarısız.",
            )
        if notes or questions:
            reservation = credit_service.confirm(db, user_id, video_id, reservation)
        elif reservation.charged:
            jobs.track_follower(
                shared["id"],
                user_id,
                reservation.charge_kind,
            )
        return _deliver_shared_job(
            shared,
            reservation,
            user_id=user_id,
            subject=payload.subject,
            exam_target=exam_target,
        )

    leader = claim_work(video_id, payload.subject, focus_bkt)
    if not leader:
        # Uzun bekleme tarayıcı timeout'una yol açıyor; cache/shared bir kez bak.
        cached = cache.load(cache_key) or cache.find_cached(
            video_id, payload.subject, exam_target, focus_bucket=focus_bkt
        )
        if cached:
            return _deliver_cached_analyze(
                cached=cached,
                db=db,
                user_id=user_id,
                video_id=video_id,
                subject=payload.subject,
                reservation=reservation,
                exam_target=exam_target,
            )
        shared = jobs.find_running(video_id, payload.subject, focus_bucket=focus_bkt)
        if shared:
            status = shared.get("status") or "running"
            notes = shared.get("notes") or []
            questions = shared.get("questions") or []
            if status == "error":
                credit_service.refund(db, user_id, reservation)
                raise HTTPException(
                    status_code=502,
                    detail=shared.get("error") or "Paylaşılan analiz başarısız.",
                )
            if notes or questions:
                reservation = credit_service.confirm(db, user_id, video_id, reservation)
            elif reservation.charged:
                jobs.track_follower(
                    shared["id"],
                    user_id,
                    reservation.charge_kind,
                )
            return _deliver_shared_job(
                shared,
                reservation,
                user_id=user_id,
                subject=payload.subject,
                exam_target=exam_target,
            )
        credit_service.refund(db, user_id, reservation)
        raise _busy_http(
            ServiceBusyError("Aynı video çözülüyor. 15 saniye sonra tekrar dene.")
        )

    hold_lock = False
    try:
        jobs.ensure_capacity()
        job_id = jobs.create_job(
            user_id=user_id,
            video_id=video_id,
            video_url=canonical_url,
            subject=payload.subject,
            chunks_total=1,
            overlay=overlay,
            focus_bucket=focus_bkt,
        )
        hold_lock = True
        if lines is None:
            threading.Thread(
                target=_fetch_then_analyze_job,
                args=(
                    job_id,
                    user_id,
                    video_id,
                    canonical_url,
                    payload.subject,
                    payload.question_count,
                    exam_target,
                    subject_meta,
                    cache_key,
                    extra_keys,
                    reservation,
                    focus_start,
                    focus_bkt,
                ),
                daemon=True,
                name=f"analyze-{job_id}",
            ).start()
        else:
            threading.Thread(
                target=_analyze_lines_job,
                args=(
                    job_id,
                    lines,
                    user_id,
                    video_id,
                    canonical_url,
                    payload.subject,
                    payload.question_count,
                    exam_target,
                    subject_meta,
                    cache_key,
                    extra_keys,
                    reservation,
                    focus_start,
                    focus_bkt,
                ),
                daemon=True,
                name=f"analyze-{job_id}",
            ).start()
        return AnalyzeResponse(
            video_id=video_id,
            video_url=canonical_url,
            subject=payload.subject,
            notes=[],
            questions=[],
            job_id=job_id,
            job_status="running",
            chunks_done=0,
            chunks_total=1,
            **overlay,
        )
    except ServiceBusyError as exc:
        credit_service.refund(db, user_id, reservation)
        raise _busy_http(exc) from exc
    except ValueError as exc:
        credit_service.refund(db, user_id, reservation)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExhaustedError as exc:
        credit_service.refund(db, user_id, reservation)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ConfigurationError as exc:
        credit_service.refund(db, user_id, reservation)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        credit_service.refund(db, user_id, reservation)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        credit_service.refund(db, user_id, reservation)
        raise HTTPException(
            status_code=502,
            detail=f"Altyazı veya LLM adımı başarısız: {exc}",
        ) from exc
    finally:
        if leader and not hold_lock:
            release_work(video_id, payload.subject, focus_bkt)


@app.post("/analyze/jobs/{job_id}/cancel")
@limiter.limit("20/minute")
def analyze_job_cancel(request: Request, job_id: str) -> dict:
    """Yanlış link / vazgeç: bekleyen LLM işini durdur (mümkünse kredi iadesi)."""
    from app.services import analyze_jobs as jobs

    job = jobs.snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analiz işi bulunamadı.")
    viewer = actor(request)
    owner = str(job.get("user_id") or "")
    if owner and owner != viewer:
        raise HTTPException(status_code=403, detail="Bu analizi sadece sahibi iptal edebilir.")
    if job.get("status") != "running":
        return {"ok": True, "job_id": job_id, "status": job.get("status") or "done"}
    jobs.request_cancel(job_id)
    return {"ok": True, "job_id": job_id, "status": "cancelling"}


@app.get("/analyze/jobs/{job_id}", response_model=AnalyzeResponse)
@limiter.limit("40/minute")
def analyze_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    from app.services import analyze_jobs as jobs

    job = jobs.snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analiz işi bulunamadı.")
    viewer = actor(request)
    if job.get("user_id") == viewer:
        overlay = job.get("overlay") or {}
    else:
        overlay = credit_service.overlay_view(credit_service.snapshot(db, viewer))
    notes = job.get("notes") or []
    questions = job.get("questions") or []
    status = job.get("status") or "running"
    if status == "error":
        kind = jobs.mark_follower_settled(job_id, viewer)
        if kind:
            try:
                credit_service.refund_charged(db, viewer, kind)
            except Exception:
                logger.exception("Takipçi iadesi başarısız %s", viewer)
    elif notes or questions:
        kind = jobs.mark_follower_settled(job_id, viewer)
        if kind:
            try:
                credit_service.confirm_charged(db, viewer, job["video_id"], kind)
            except Exception:
                logger.exception("Takipçi confirm başarısız %s", viewer)
        from app.services.exams import exam_of

        _persist_notebook(
            user_id=viewer,
            subject=job.get("subject"),
            video_id=job["video_id"],
            video_url=job["video_url"],
            notes=notes,
            questions=questions,
            persona=job.get("teacher_persona"),
            exam_target=exam_of(db, viewer),
        )
    return AnalyzeResponse(
        video_id=job["video_id"],
        video_url=job["video_url"],
        subject=job["subject"] or None,
        notes=notes,
        questions=questions,
        teacher_persona=job["teacher_persona"],
        job_id=job["id"],
        job_status=job["status"],
        job_error=job.get("error") or "",
        chunks_done=job["chunks_done"],
        chunks_total=job["chunks_total"],
        **overlay,
    )


@app.get("/notebook/{user_id}", response_model=NotebookResponse)
@limiter.limit("30/minute")
def list_notebook(
    request: Request,
    user_id: str,
    subject: str | None = None,
    db: Session = Depends(get_db),
) -> NotebookResponse:
    from app.services.exams import exam_of

    data = notebook_service.list_items(
        db,
        user_id,
        subject=subject,
        exam_target=exam_of(db, user_id),
    )
    from app.models.schemas import SavedNoteItem, SavedQuestionItem, NotebookSubjectCount

    notes_out = []
    for item in data.get("notes") or []:
        try:
            notes_out.append(SavedNoteItem.model_validate(item))
        except Exception as exc:
            logger.warning("Not satırı atlandı: %s", exc)
    questions_out = []
    for item in data.get("questions") or []:
        try:
            questions_out.append(SavedQuestionItem.model_validate(item))
        except Exception as exc:
            logger.warning("Soru satırı atlandı: %s", exc)
    subjects_out = []
    for item in data.get("subjects") or []:
        try:
            subjects_out.append(NotebookSubjectCount.model_validate(item))
        except Exception:
            continue
    return NotebookResponse(
        user_id=str(data.get("user_id") or user_id),
        subject=data.get("subject"),
        subjects=subjects_out,
        notes=notes_out,
        questions=questions_out,
    )


@app.post("/ads/unlock", response_model=AdUnlockResponse)
def ads_unlock(
    payload: AdUnlockRequest, db: Session = Depends(get_db)
) -> AdUnlockResponse:
    view = credit_service.mark_ad_watched(db, payload.user_id)
    return AdUnlockResponse(
        ok=True,
        is_ad_tier=bool(view["is_ad_tier"]),
        daily_ad_credits=int(view["daily_ad_credits"]),
        daily_ad_limit=int(view["daily_ad_limit"]),
        is_in_trial_period=bool(view["is_in_trial_period"]),
    )


@app.get("/subscription/status", response_model=SubscriptionStatusResponse)
def subscription_status(user_id: str, db: Session = Depends(get_db)) -> SubscriptionStatusResponse:
    from app.services import billing as billing_service

    user = penalty_service.get_or_create_user(db, user_id)
    billing_service.refresh_entitlement(db, user)
    db.commit()
    data = billing_service.public_status(user)
    return SubscriptionStatusResponse(
        ok=True,
        is_premium=bool(data["is_premium"]),
        subscription_status=str(data["subscription_status"]),
        product_id=str(data["product_id"]),
        expires_at=data["expires_at"],
        sandbox=bool(data["sandbox"]),
        package_name=str(data["package_name"]),
        plans=data["plans"],
        message="Tilko Pro aktif." if data["is_premium"] else "",
    )


@app.post("/subscription/verify", response_model=SubscriptionStatusResponse)
@limiter.limit("8/minute")
def subscription_verify(
    request: Request,
    payload: SubscriptionVerifyRequest,
    db: Session = Depends(get_db),
) -> SubscriptionStatusResponse:
    from app.services import billing as billing_service

    raw = payload.model_dump()
    webhook = bool(getattr(request.state, "play_webhook", False) or raw.get("message"))
    if webhook:
        if settings.is_production or not settings.play_billing_sandbox:
            if not play_webhook_ok(request):
                raise HTTPException(status_code=401, detail="Play webhook anahtarı geçersiz.")
        elif not play_webhook_ok(request) and (settings.play_webhook_secret or "").strip():
            raise HTTPException(status_code=401, detail="Play webhook anahtarı geçersiz.")
        try:
            result = billing_service.handle_rtdn(db, raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return SubscriptionStatusResponse(
            ok=bool(result.get("ok", True)),
            is_premium=bool(result.get("is_premium", False)),
            message="Abonelik bildirimi işlendi.",
        )
    try:
        data = billing_service.verify_purchase(
            db,
            user_id=payload.user_id,
            product_id=payload.product_id,
            purchase_token=payload.purchase_token,
            order_id=payload.order_id,
            platform=payload.platform,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Play doğrulama hatası: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Google Play doğrulaması şu an yapılamadı. Biraz sonra tekrar dene.",
        ) from exc
    return SubscriptionStatusResponse.model_validate(data)


@app.post("/subscription/webhook")
@limiter.limit("30/minute")
def subscription_webhook(
    request: Request,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
) -> dict:
    from app.services import billing as billing_service

    if not play_webhook_ok(request):
        if settings.is_production or not settings.play_billing_sandbox:
            raise HTTPException(status_code=401, detail="Play webhook anahtarı geçersiz.")
        if (settings.play_webhook_secret or "").strip():
            raise HTTPException(status_code=401, detail="Play webhook anahtarı geçersiz.")
    try:
        return billing_service.handle_rtdn(db, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/credits/grant", response_model=AdminCreditsGrantResponse)
def admin_credits_grant(
    payload: AdminCreditsGrantRequest, db: Session = Depends(get_db)
) -> AdminCreditsGrantResponse:
    uid = (payload.user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id gerekli.")
    view = credit_service.grant_credits(
        db,
        uid,
        credits=payload.credits,
        premium=payload.premium,
    )
    return AdminCreditsGrantResponse(
        ok=True,
        user_id=uid,
        ai_credits_left=int(view["ai_credits_left"]),
        ai_credit_limit=int(view["ai_credit_limit"]),
        is_premium=bool(view["is_premium"]),
        is_in_trial_period=bool(view["is_in_trial_period"]),
        message=(
            "Pro (sınırsız test) açık."
            if view["is_premium"]
            else f"Kredi: {view['ai_credits_left']}/{view['ai_credit_limit']}"
        ),
    )


def _iso_dt(value) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:  # noqa: BLE001
        return str(value)


@app.get("/admin/users", response_model=AdminUserListResponse)
def admin_users_list(
    q: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    from sqlalchemy import or_, select

    from app.database.models import User
    from app.services import billing as billing_service

    cap = max(1, min(int(limit or 100), 300))
    needle = (q or "").strip().lower()
    stmt = select(User).order_by(User.created_at.desc()).limit(cap)
    if needle:
        like = f"%{needle}%"
        stmt = (
            select(User)
            .where(
                or_(
                    User.user_id.ilike(like),
                    User.email.ilike(like),
                    User.phone.ilike(like),
                    User.display_name.ilike(like),
                )
            )
            .order_by(User.created_at.desc())
            .limit(cap)
        )
    rows = list(db.scalars(stmt).all())
    users: list[AdminUserRow] = []
    for user in rows:
        billing_service.refresh_entitlement(db, user)
        users.append(
            AdminUserRow(
                user_id=user.user_id,
                display_name=(user.display_name or "").strip(),
                email=(user.email or "").strip(),
                phone=(user.phone or "").strip(),
                exam_target=(user.exam_target or "").strip(),
                role=(user.role or "student").strip() or "student",
                is_premium=bool(user.is_premium),
                subscription_status=(user.subscription_status or "").strip(),
                subscription_expires_at=_iso_dt(user.subscription_expires_at),
                ai_credits_left=int(user.ai_credits_left or 0),
                created_at=_iso_dt(user.created_at),
                has_google=bool((user.google_sub or "").strip()),
                has_password=bool((user.password_hash or "").strip()),
            )
        )
    return AdminUserListResponse(users=users, count=len(users))


@app.post("/admin/users/grant-pro", response_model=AdminGrantProResponse)
def admin_users_grant_pro(
    payload: AdminGrantProRequest, db: Session = Depends(get_db)
) -> AdminGrantProResponse:
    from app.services import billing as billing_service
    from app.services.penalty import get_or_create_user

    uid = (payload.user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id gerekli.")
    user = get_or_create_user(db, uid)
    billing_service.refresh_entitlement(db, user)
    if payload.revoke:
        user.is_premium = False
        user.subscription_status = "admin_revoked"
        user.subscription_expires_at = None
        db.add(user)
        db.commit()
        db.refresh(user)
        return AdminGrantProResponse(
            ok=True,
            user_id=uid,
            is_premium=False,
            subscription_status=user.subscription_status or "",
            subscription_expires_at=None,
            message="Pro kaldırıldı.",
        )
    billing_service.grant_pro_subscription(db, user, days=int(payload.days or 31))
    user.subscription_status = "admin"
    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminGrantProResponse(
        ok=True,
        user_id=uid,
        is_premium=bool(user.is_premium),
        subscription_status=user.subscription_status or "",
        subscription_expires_at=_iso_dt(user.subscription_expires_at),
        message=f"Pro verildi ({payload.days} gün).",
    )


@app.post("/admin/users/set-password", response_model=AdminSetPasswordResponse)
def admin_users_set_password(
    payload: AdminSetPasswordRequest, db: Session = Depends(get_db)
) -> AdminSetPasswordResponse:
    from app.services import password_reset as reset_service

    try:
        data = reset_service.admin_set_password(
            db, payload.user_id, payload.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminSetPasswordResponse.model_validate(data)


@app.post("/admin/users/update", response_model=AdminUserUpdateResponse)
def admin_users_update(
    payload: AdminUserUpdateRequest, db: Session = Depends(get_db)
) -> AdminUserUpdateResponse:
    from app.services import password_reset as reset_service

    try:
        data = reset_service.admin_update_user(
            db,
            user_id=payload.user_id,
            display_name=payload.display_name,
            email=payload.email,
            phone=payload.phone,
            exam_target=payload.exam_target,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminUserUpdateResponse.model_validate(data)


@app.post("/admin/promo/create", response_model=PromoCreateResponse)
def admin_promo_create(
    payload: PromoCreateRequest, db: Session = Depends(get_db)
) -> PromoCreateResponse:
    from app.services import promo as promo_service

    try:
        data = promo_service.create_promo(
            db,
            code=payload.code,
            discount_type=payload.discount_type,
            value=payload.value,
            max_uses=payload.max_uses,
            quantity=payload.quantity,
            expires_at=payload.expires_at,
            created_by_teacher_id=payload.created_by_teacher_id,
            enroll_to_class=payload.enroll_to_class,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromoCreateResponse.model_validate(data)


@app.get("/admin/promo/list", response_model=PromoListResponse)
def admin_promo_list(db: Session = Depends(get_db)) -> PromoListResponse:
    from app.services import promo as promo_service

    return PromoListResponse.model_validate(promo_service.list_promos(db))


@app.get("/admin/exams/list", response_model=ExamScheduleListResponse)
def admin_exams_list(db: Session = Depends(get_db)) -> ExamScheduleListResponse:
    from app.services import exams as exam_service

    return ExamScheduleListResponse.model_validate(exam_service.list_exam_schedules(db))


@app.post("/admin/exams/update", response_model=ExamScheduleItem)
def admin_exams_update(
    payload: ExamScheduleUpdateRequest, db: Session = Depends(get_db)
) -> ExamScheduleItem:
    from app.services import exams as exam_service

    try:
        data = exam_service.update_exam_schedule(db, payload.exam_target, payload.exam_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExamScheduleItem.model_validate(data)


@app.post("/admin/exams/today", response_model=ExamScheduleListResponse)
def admin_exams_today(
    payload: ExamClockUpdateRequest, db: Session = Depends(get_db)
) -> ExamScheduleListResponse:
    from app.services import exams as exam_service

    try:
        data = exam_service.update_clock_today(
            db, exam_date=payload.exam_date, reset=payload.reset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExamScheduleListResponse.model_validate(data)


@app.post("/billing/apply-promo", response_model=PromoApplyResponse)
@limiter.limit("20/minute")
def billing_apply_promo(
    request: Request,
    payload: PromoApplyRequest,
    db: Session = Depends(get_db),
) -> PromoApplyResponse:
    from app.services import promo as promo_service

    try:
        data = promo_service.apply_promo(
            db,
            payload.user_id,
            payload.code,
            payload.product_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PromoApplyResponse.model_validate(data)


def _teacher_http(exc: Exception) -> None:
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/teacher/students", response_model=TeacherClassroomResponse)
def teacher_students(request: Request, db: Session = Depends(get_db)) -> TeacherClassroomResponse:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.list_classroom(db, actor(request))
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherClassroomResponse.model_validate(data)


@app.get(
    "/teacher/student-analysis/{student_id}",
    response_model=TeacherStudentAnalysisResponse,
)
def teacher_student_analysis(
    student_id: str, request: Request, db: Session = Depends(get_db)
) -> TeacherStudentAnalysisResponse:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.student_analysis(db, actor(request), student_id)
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherStudentAnalysisResponse.model_validate(data)


@app.post("/teacher/share-resource", response_model=TeacherAssignmentView)
def teacher_share_resource(
    payload: TeacherShareRequest, request: Request, db: Session = Depends(get_db)
) -> TeacherAssignmentView:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.share_resource(
            db,
            actor(request),
            title=payload.title,
            topic=payload.topic,
            question_text=payload.question_text,
            options=payload.options,
            correct=payload.correct,
            explanation=payload.explanation,
            student_ids=payload.student_ids,
        )
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherAssignmentView.model_validate(data)


@app.get("/teacher/assignments", response_model=TeacherAssignmentListResponse)
def teacher_assignments(
    request: Request, db: Session = Depends(get_db)
) -> TeacherAssignmentListResponse:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.list_teacher_assignments(db, actor(request))
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherAssignmentListResponse.model_validate(data)


@app.post("/teacher/promo/create", response_model=PromoCreateResponse)
def teacher_promo_create(
    payload: PromoCreateRequest, request: Request, db: Session = Depends(get_db)
) -> PromoCreateResponse:
    from app.services import promo as promo_service
    from app.services import teacher as teacher_service

    try:
        teacher_service.require_teacher(db, actor(request))
        data = promo_service.create_promo(
            db,
            code=payload.code,
            discount_type=payload.discount_type,
            value=payload.value,
            max_uses=payload.max_uses,
            quantity=payload.quantity,
            expires_at=payload.expires_at,
            created_by_teacher_id=actor(request),
            enroll_to_class=payload.enroll_to_class,
        )
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return PromoCreateResponse.model_validate(data)


@app.get("/teacher/promo/list", response_model=PromoListResponse)
def teacher_promo_list(request: Request, db: Session = Depends(get_db)) -> PromoListResponse:
    from app.services import promo as promo_service
    from app.services import teacher as teacher_service

    try:
        teacher_service.require_teacher(db, actor(request))
        data = promo_service.list_promos(db, teacher_id=actor(request))
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return PromoListResponse.model_validate(data)


@app.get("/student/assignments", response_model=TeacherAssignmentListResponse)
def student_assignments(
    request: Request, db: Session = Depends(get_db)
) -> TeacherAssignmentListResponse:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.list_student_assignments(db, actor(request))
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherAssignmentListResponse.model_validate(data)


@app.post("/student/assignments/submit", response_model=TeacherAssignmentSubmitResponse)
def student_assignment_submit(
    payload: TeacherAssignmentSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TeacherAssignmentSubmitResponse:
    from app.services import teacher as teacher_service

    try:
        data = teacher_service.submit_assignment(
            db, actor(request), payload.assignment_id, payload.chosen
        )
    except (ValueError, PermissionError) as exc:
        _teacher_http(exc)
    return TeacherAssignmentSubmitResponse.model_validate(data)


@app.get("/admin/rag-status")
def admin_rag_status(
    request: Request,
    db: Session = Depends(get_db),
    exam_target: str = "",
) -> dict:
    from app.services import rag as rag_service

    return rag_service.rag_status(db, exam_target or None)


@app.post("/admin/feed-osym-archives")
@limiter.limit("6/minute")
async def admin_feed_osym_archives(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    from app.services import rag as rag_service

    exam_target = request.query_params.get("exam_target") or ""
    try:
        exam_year = int(request.query_params.get("exam_year") or 0)
    except ValueError:
        exam_year = 0
    uploads: list[tuple[str, bytes]] = []
    urls: list[str] = []
    scan_inbox: bool | None = None
    ctype = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ctype:
        form = await request.form()
        exam_target = str(form.get("exam_target") or exam_target)
        try:
            exam_year = int(form.get("exam_year") or exam_year or 0)
        except (TypeError, ValueError):
            exam_year = 0
        if form.get("scan_inbox") is not None:
            scan_inbox = str(form.get("scan_inbox")).strip().lower() in {"1", "true", "yes", "on"}
        urls.extend(rag_service.parse_archive_urls(form.get("urls")))
        urls.extend(rag_service.parse_archive_urls(form.getlist("url")))
        for key in ("files", "file"):
            for item in form.getlist(key):
                read = getattr(item, "read", None)
                if not callable(read):
                    continue
                data = await read()
                name = str(getattr(item, "filename", None) or "upload.txt")
                if data:
                    uploads.append((name, data))
    elif "application/json" in ctype:
        body = await request.json()
        if isinstance(body, dict):
            exam_target = str(body.get("exam_target") or exam_target)
            try:
                exam_year = int(body.get("exam_year") or exam_year or 0)
            except (TypeError, ValueError):
                exam_year = 0
            if "scan_inbox" in body:
                scan_inbox = bool(body.get("scan_inbox"))
            urls.extend(rag_service.parse_archive_urls(body.get("urls")))
            urls.extend(rag_service.parse_archive_urls(body.get("url")))
    try:
        return rag_service.feed_archives(
            db,
            exam_target=exam_target or None,
            exam_year=exam_year,
            uploads=uploads,
            urls=urls,
            scan_inbox=scan_inbox,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
@app.post("/save_trap", response_model=SaveTrapResponse)
@limiter.limit("20/minute")
def save_trap(
    request: Request, payload: SaveTrapRequest, db: Session = Depends(get_db)
) -> SaveTrapResponse:
    row = trap_service.save_wrong_trap(db, payload)
    badges = gamification.record_wrong(db, payload.user_id)
    title = gamification.address_for(db, payload.user_id)
    warning = (
        f"Hey {title}, bilgiden değil süreden kaybediyorsun. ÖSYM seni 60 saniyeden fazla oyaladı."
        if row.time_trap_triggered
        else ""
    )
    return SaveTrapResponse(
        trap=TrapItem.model_validate(trap_service.to_public(row)),
        time_trap_triggered=bool(row.time_trap_triggered),
        warning=warning,
        new_badges=badges,
    )


@app.get("/daily_missions/{user_id}", response_model=DailyMissionsResponse)
def daily_missions(user_id: str, db: Session = Depends(get_db)) -> DailyMissionsResponse:
    rows = trap_service.due_traps(db, user_id)
    weak = diagnostic_service.status(db, user_id).get("weak_topics") or []
    rows = trap_service.prioritize_weak(rows, weak)
    traps = [TrapItem.model_validate(trap_service.to_public(row)) for row in rows]
    return DailyMissionsResponse(user_id=user_id, due_count=len(traps), traps=traps)


@app.get("/traps/{user_id}", response_model=DailyMissionsResponse)
def list_traps(user_id: str, db: Session = Depends(get_db)) -> DailyMissionsResponse:
    rows = trap_service.all_traps(db, user_id)
    weak = diagnostic_service.status(db, user_id).get("weak_topics") or []
    rows = trap_service.prioritize_weak(rows, weak)
    traps = [TrapItem.model_validate(trap_service.to_public(row)) for row in rows]
    return DailyMissionsResponse(user_id=user_id, due_count=len(traps), traps=traps)


@app.post("/complete_trap", response_model=CompleteTrapResponse)
def complete_trap(
    payload: CompleteTrapRequest, db: Session = Depends(get_db)
) -> CompleteTrapResponse:
    try:
        row = trap_service.complete_trap(db, payload.user_id, payload.trap_id, payload.chosen)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ok = (payload.chosen or "").strip().upper()[:1] == (row.correct or "").strip().upper()[:1]
    game = gamification.after_complete(
        db,
        payload.user_id,
        correct=ok,
        time_trap=bool(row.time_trap_triggered),
    )
    title = gamification.address_for(db, payload.user_id)
    if ok:
        message = (
            f"Helal olsun {title}. Sonraki tekrar {row.review_count}. basamak: "
            f"{row.next_review_date.isoformat() if row.next_review_date else '?'}"
        )
    else:
        message = f"Hey {title}, yine kaçtı. 24 saat sonra aynı tuzak seni bekliyor."
    if game.get("notebook_cleared"):
        message += f" Defter temiz. Seri {game.get('streak', 0)} gün."
    return CompleteTrapResponse(
        trap=TrapItem.model_validate(trap_service.to_public(row)),
        correct=ok,
        message=message,
        game=GameEvent.model_validate(game),
    )


@app.get("/progress/{user_id}", response_model=ProgressResponse)
def progress(
    request: Request, user_id: str, db: Session = Depends(get_db)
) -> ProgressResponse:
    from app.services import anti_cheat

    ip_hash = anti_cheat.hash_ip(anti_cheat.client_ip(request))
    return ProgressResponse.model_validate(
        gamification.public_progress(db, user_id, ip_hash=ip_hash)
    )


@app.post("/user/set-exam-target", response_model=SetExamTargetResponse)
def set_exam_target(
    request: Request,
    payload: SetExamTargetRequest,
    db: Session = Depends(get_db),
) -> SetExamTargetResponse:
    from app.services import exams as exam_service
    from app.services import anti_cheat

    try:
        data = exam_service.set_exam_target(
            db,
            payload.user_id,
            payload.exam_target,
            ip_hash=anti_cheat.hash_ip(anti_cheat.client_ip(request)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SetExamTargetResponse.model_validate(data)


@app.get("/user/exam-countdown", response_model=ExamCountdownResponse)
def exam_countdown(user_id: str = "local", db: Session = Depends(get_db)) -> ExamCountdownResponse:
    from app.services.exams import countdown, exam_of

    target = exam_of(db, user_id)
    return ExamCountdownResponse.model_validate(countdown(target, db=db))


@app.get("/questions", response_model=QuestionBankResponse)
def questions_bank(user_id: str = "local", db: Session = Depends(get_db)) -> QuestionBankResponse:
    from app.services.exams import catalog_for, exam_of, label_for

    target = exam_of(db, user_id)
    bank = diagnostic_service.bank_for(target)
    pack = catalog_for(target)
    return QuestionBankResponse(
        exam_target=target,
        exam_label=label_for(target),
        family=pack["family"],
        subjects=pack["subjects"],
        questions=[diagnostic_service.public_question(item) for item in bank],
    )


@app.post("/user/set-target-score", response_model=SetTargetScoreResponse)
def set_target_score(
    payload: SetTargetScoreRequest, db: Session = Depends(get_db)
) -> SetTargetScoreResponse:
    from app.services import exams as exam_service

    try:
        data = exam_service.set_target_score(db, payload.user_id, payload.target_score)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SetTargetScoreResponse.model_validate(data)


@app.get("/motivational-quote", response_model=MotivationalQuoteResponse)
def motivational_quote(
    user_id: str, db: Session = Depends(get_db)
) -> MotivationalQuoteResponse:
    from app.services import quotes as quote_service

    try:
        data = quote_service.daily_quote(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MotivationalQuoteResponse.model_validate(data)


@app.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(limit: int = 20, db: Session = Depends(get_db)) -> LeaderboardResponse:
    return LeaderboardResponse(entries=gamification.leaderboard(db, limit=min(limit, 50)))


@app.get("/daily-challenge", response_model=DailyChallengeItem)
def get_daily_challenge(
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> DailyChallengeItem:
    return DailyChallengeItem.model_validate(hunt_service.today_state(db, user_id))


@app.post("/daily-challenge/start", response_model=DailyChallengeStartResponse)
def start_daily_challenge(
    payload: DailyChallengeStartRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DailyChallengeStartResponse:
    try:
        result = hunt_service.begin_hunt(
            db,
            user_id=payload.user_id,
            challenge_id=payload.challenge_id,
            device_id=payload.device_id,
            ip_hash=anti_cheat.hash_ip(anti_cheat.client_ip(request)),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DailyChallengeStartResponse.model_validate(result)


@app.post("/daily-challenge/submit", response_model=DailyChallengeSubmitResponse)
@limiter.limit("12/minute")
def submit_daily_challenge(
    payload: DailyChallengeSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DailyChallengeSubmitResponse:
    try:
        result = hunt_service.submit(
            db,
            user_id=payload.user_id,
            chosen=payload.chosen,
            challenge_id=payload.challenge_id,
            device_id=payload.device_id,
            ip_hash=anti_cheat.hash_ip(anti_cheat.client_ip(request)),
            identity_hash=payload.identity_hash,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DailyChallengeSubmitResponse.model_validate(result)


@app.get("/daily-challenge/leaderboard", response_model=DailyChallengeLeaderboardResponse)
def daily_challenge_leaderboard(
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> DailyChallengeLeaderboardResponse:
    challenge = hunt_service.ensure_today(db, user_id=user_id)
    entries = prize_service.attach_badges(
        db, hunt_service.leaderboard_entries(db, challenge.id)
    )
    full = hunt_service.leaderboard_entries(db, challenge.id, limit=10_000)
    meta = prize_service.prize_meta(db)
    return DailyChallengeLeaderboardResponse(
        challenge_id=challenge.id,
        date=challenge.date.isoformat() if challenge.date else None,
        title="Kurnazlar Listesi",
        entries=entries,
        viewer_rank=hunt_service.rank_for(full, user_id) if user_id else None,
        **meta,
    )


@app.get("/bulletin/latest", response_model=BulletinResponse)
def latest_bulletin(db: Session = Depends(get_db)) -> BulletinResponse:
    row = bulletin_service.load_bulletin(db)
    if row is None:
        row = bulletin_service.generate_bulletin(db)
    return BulletinResponse.model_validate(bulletin_service.bulletin_public(row))


@app.post("/bulletin/generate", response_model=BulletinResponse)
def generate_bulletin(week_id: str | None = None, db: Session = Depends(get_db)) -> BulletinResponse:
    row = bulletin_service.generate_bulletin(db, week_id)
    return BulletinResponse.model_validate(bulletin_service.bulletin_public(row))


@app.get("/bulletin/{week_id}.html")
def bulletin_html(week_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = bulletin_service.load_bulletin(db, week_id)
    if row is None:
        row = bulletin_service.generate_bulletin(db, week_id)
    path = Path(row.html_path)
    if not path.exists():
        row = bulletin_service.generate_bulletin(db, week_id)
        path = Path(row.html_path)
    return FileResponse(path, media_type="text/html")


@app.post("/api/penalty", response_model=PenaltyStatus)
def apply_penalty(payload: PenaltyRequest, db: Session = Depends(get_db)) -> PenaltyStatus:
    row = penalty_service.apply_penalty(db, payload.user_id)
    trap = TrapItem.model_validate(penalty_service.next_question(db, payload.user_id))
    return PenaltyStatus(
        user_id=row.user_id,
        is_penalized=True,
        penalty_clear_count=0,
        needed=penalty_service.UNLOCK_STREAK,
        trap=trap,
        message=f"Hey {gamification.address_for(db, payload.user_id)}, odak bozuldu. Kilidi açmak için peş peşe 3 doğru.",
    )


@app.post("/api/penalty/answer", response_model=PenaltyAnswerResponse)
def penalty_answer(
    payload: PenaltyAnswerRequest, db: Session = Depends(get_db)
) -> PenaltyAnswerResponse:
    try:
        result = penalty_service.register_answer(
            db, payload.user_id, payload.trap_id, payload.chosen
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    trap = None
    if result["is_penalized"]:
        trap = TrapItem.model_validate(
            penalty_service.next_question(db, payload.user_id, payload.trap_id)
        )
    title = gamification.address_for(db, payload.user_id)
    if result["unlocked"]:
        message = f"Helal olsun {title}, kilit açıldı. Geri dön, seansı bitir."
    elif result["correct"]:
        message = f"Doğru {title}. Seri {result['streak']}/{result['needed']}."
    else:
        message = f"Hey {title}, yanlış. Seri sıfırlandı. Baştan 3 doğru."
    return PenaltyAnswerResponse(
        **result,
        trap=trap,
        message=message,
    )


@app.post("/api/clear_penalty", response_model=PenaltyStatus)
def clear_penalty(payload: ClearPenaltyRequest, db: Session = Depends(get_db)) -> PenaltyStatus:
    try:
        row = penalty_service.clear_penalty(db, payload.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return PenaltyStatus(
        user_id=row.user_id,
        is_penalized=False,
        penalty_clear_count=0,
        needed=penalty_service.UNLOCK_STREAK,
        message=f"Helal olsun {gamification.address_for(db, payload.user_id)}, kilit kalktı.",
    )


@app.get("/api/penalty/{user_id}", response_model=PenaltyStatus)
def penalty_status(user_id: str, db: Session = Depends(get_db)) -> PenaltyStatus:
    row = penalty_service.get_or_create_user(db, user_id)
    trap = None
    if row.is_penalized:
        trap = TrapItem.model_validate(penalty_service.next_question(db, user_id))
    return PenaltyStatus(
        user_id=row.user_id,
        is_penalized=bool(row.is_penalized),
        penalty_clear_count=row.penalty_clear_count,
        needed=penalty_service.UNLOCK_STREAK,
        trap=trap,
    )


@app.post("/api/pomodoro/complete", response_model=PomodoroCompleteResponse)
def pomodoro_complete(
    payload: PomodoroCompleteRequest, db: Session = Depends(get_db)
) -> PomodoroCompleteResponse:
    result = gamification.complete_pomodoro(db, payload.user_id, payload.session_id)
    return PomodoroCompleteResponse.model_validate(result)


@app.get("/api/prizes/me", response_model=PrizeView)
def my_prize(user_id: str, db: Session = Depends(get_db)) -> PrizeView:
    return PrizeView.model_validate(prize_service.profile_prize(db, user_id))


@app.post("/api/prizes/settle", response_model=PrizeSettleResponse)
def settle_prizes(
    request: Request, month: str | None = None, db: Session = Depends(get_db)
) -> PrizeSettleResponse:
    if not admin_ok(request):
        raise HTTPException(status_code=401, detail="Admin anahtarı geçersiz.")
    try:
        result = prize_service.settle_month(db, month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PrizeSettleResponse.model_validate(result)


@app.get("/diagnostic/exam", response_model=DiagnosticExamResponse)
def diagnostic_exam(
    kind: str = "baseline",
    user_id: str = "local",
    db: Session = Depends(get_db),
) -> DiagnosticExamResponse:
    questions = diagnostic_service.exam_for(user_id, kind, db=db)
    label = "checkup" if (kind or "").lower() == "checkup" else "baseline"
    return DiagnosticExamResponse(kind=label, questions=questions)


@app.post("/diagnostic/submit", response_model=DiagnosticReport)
def diagnostic_submit(
    request: Request,
    payload: DiagnosticSubmitRequest,
    db: Session = Depends(get_db),
) -> DiagnosticReport:
    from app.services import anti_cheat

    try:
        result = diagnostic_service.submit_baseline(
            db,
            payload.user_id,
            [item.model_dump() for item in payload.answers],
            ip_hash=anti_cheat.hash_ip(anti_cheat.client_ip(request)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return DiagnosticReport.model_validate(result)


@app.post("/diagnostic/checkup-submit", response_model=CheckupSubmitResponse)
def diagnostic_checkup_submit(
    payload: DiagnosticSubmitRequest, db: Session = Depends(get_db)
) -> CheckupSubmitResponse:
    try:
        result = diagnostic_service.submit_checkup(
            db,
            payload.user_id,
            [item.model_dump() for item in payload.answers],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return CheckupSubmitResponse.model_validate(result)


@app.get("/diagnostic/progress-history", response_model=ProgressHistoryResponse)
def diagnostic_progress_history(
    user_id: str, db: Session = Depends(get_db)
) -> ProgressHistoryResponse:
    return ProgressHistoryResponse.model_validate(
        diagnostic_service.progress_history(db, user_id)
    )


@app.get("/exam/catalog", response_model=DynamicExamCatalogResponse)
def exam_catalog(
    user_id: str = "local",
    exam_target: str = "",
    db: Session = Depends(get_db),
) -> DynamicExamCatalogResponse:
    return DynamicExamCatalogResponse.model_validate(
        dynamic_exam_service.catalog(db, user_id, exam_target or None)
    )


@app.post("/exam/generate-dynamic", response_model=DynamicExamGenerateResponse)
@app.post("/exam/generate", response_model=DynamicExamGenerateResponse)
@limiter.limit("4/minute")
def generate_dynamic_exam(
    request: Request,
    payload: DynamicExamGenerateRequest,
    db: Session = Depends(get_db),
) -> DynamicExamGenerateResponse:
    try:
        result = dynamic_exam_service.generate(
            db,
            user_id=payload.user_id,
            exam_target=None,
            subjects=payload.subjects,
            question_count=payload.question_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DynamicExamGenerateResponse.model_validate(result)


@app.get("/exam/dynamic/{exam_id}", response_model=DynamicExamGenerateResponse)
def get_dynamic_exam(
    exam_id: int, user_id: str = "local", db: Session = Depends(get_db)
) -> DynamicExamGenerateResponse:
    try:
        result = dynamic_exam_service.get_exam(db, user_id, exam_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DynamicExamGenerateResponse.model_validate(result)


@app.post("/exam/submit-dynamic", response_model=DynamicExamReport)
@limiter.limit("8/minute")
def submit_dynamic_exam(
    request: Request,
    payload: DynamicExamSubmitRequest,
    db: Session = Depends(get_db),
) -> DynamicExamReport:
    try:
        result = dynamic_exam_service.submit(
            db,
            user_id=payload.user_id,
            exam_id=payload.exam_id,
            answers=[item.model_dump() for item in payload.answers],
            time_spent_seconds=payload.time_spent_seconds,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return DynamicExamReport.model_validate(result)


@app.post("/questions/report", response_model=ReportQuestionResponse)
def report_question(
    payload: ReportQuestionRequest, db: Session = Depends(get_db)
) -> ReportQuestionResponse:
    try:
        result = report_service.report_question(
            db,
            user_id=payload.user_id,
            question_id=payload.question_id,
            reason_text=payload.reason_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ReportQuestionResponse.model_validate(result)


@app.get("/analytics/mistake-doctor", response_model=MistakeDoctorResponse)
def mistake_doctor(
    user_id: str, db: Session = Depends(get_db)
) -> MistakeDoctorResponse:
    try:
        result = doctor_service.diagnose(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MistakeDoctorResponse.model_validate(result)


@app.post("/feedback/submit", response_model=FeedbackSubmitResponse)
def submit_feedback(
    payload: FeedbackSubmitRequest, db: Session = Depends(get_db)
) -> FeedbackSubmitResponse:
    try:
        result = feedback_service.submit_feedback(
            db,
            user_id=payload.user_id,
            category=payload.category,
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FeedbackSubmitResponse.model_validate(result)


@app.get("/admin/feedback", response_model=AdminFeedbackListResponse)
def admin_feedback_list(
    status: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
) -> AdminFeedbackListResponse:
    data = feedback_service.list_feedback(db, limit=limit, status=status)
    return AdminFeedbackListResponse(
        items=[AdminFeedbackItem.model_validate(item) for item in data["items"]],
        count=int(data["count"]),
    )


@app.post("/admin/feedback/{feedback_id}/status", response_model=AdminFeedbackStatusResponse)
def admin_feedback_status(
    feedback_id: int,
    payload: AdminFeedbackStatusRequest,
    db: Session = Depends(get_db),
) -> AdminFeedbackStatusResponse:
    try:
        result = feedback_service.set_feedback_status(
            db, feedback_id, payload.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AdminFeedbackStatusResponse.model_validate(result)


@app.get("/api/penalty/{user_id}/next", response_model=PenaltyStatus)
def penalty_next(
    user_id: str,
    exclude_id: int | None = None,
    db: Session = Depends(get_db),
) -> PenaltyStatus:
    row = penalty_service.get_or_create_user(db, user_id)
    trap = TrapItem.model_validate(penalty_service.next_question(db, user_id, exclude_id))
    return PenaltyStatus(
        user_id=row.user_id,
        is_penalized=bool(row.is_penalized),
        penalty_clear_count=row.penalty_clear_count,
        needed=penalty_service.UNLOCK_STREAK,
        trap=trap,
    )


def _persist_notebook(
    *,
    user_id: str,
    subject: str | None,
    video_id: str,
    video_url: str,
    notes,
    questions,
    persona=None,
    exam_target: str | None = None,
    db: Session | None = None,
) -> None:
    """Notları Notlarım'a yazar. İstek session'ına bağlı kalmaz (rollback ile silinmesin)."""
    del db  # çağıran session ile karışmasın
    from app.database.session import SessionLocal

    if not notes and not questions:
        return
    session = SessionLocal()
    try:
        dumped = persona
        if hasattr(persona, "model_dump"):
            dumped = persona.model_dump()
        for attempt in range(2):
            try:
                notebook_service.ingest(
                    session,
                    user_id=user_id,
                    subject=subject,
                    video_id=video_id,
                    video_url=video_url,
                    notes=notes,
                    questions=questions,
                    persona=dumped if isinstance(dumped, dict) else None,
                    exam_target=exam_target,
                )
                break
            except Exception as exc:
                session.rollback()
                if attempt == 0:
                    logger.warning("Not defteri kaydı yeniden denenecek: %s", exc)
                    continue
                logger.warning("Not defteri kaydı atlandı: %s", exc)
    finally:
        session.close()


def _pack_notes(
    raw: object, video_id: str, start: int = 1, time_offset: int = 0
) -> list[NoteItem]:
    notes: list[NoteItem] = []
    for index, item in enumerate(raw or [], start=start):
        try:
            notes.append(_to_note(item, index, video_id, time_offset=time_offset))
        except Exception:
            continue
    return notes


def _pack_questions(
    raw: object, video_id: str, start: int = 1, time_offset: int = 0
) -> list[QuestionItem]:
    questions: list[QuestionItem] = []
    for index, item in enumerate(raw or [], start=start):
        try:
            questions.append(_to_question(item, index, video_id, time_offset=time_offset))
        except Exception:
            continue
    return questions


def _public_analyze_error(exc: BaseException) -> str:
    text = str(exc).strip() or "Analiz başarısız."
    low = text.lower()
    if "api_key" in low or "bearer" in low:
        return "Analiz şu an tamamlanamadı. Biraz sonra tekrar dene."
    if "timeout" in low or "timed out" in low or "time-out" in low or "gecikti" in low or "yavaş kaldı" in low:
        return "Analiz şu an yoğun. Biraz sonra tekrar dene."
    if "request too large" in low or "reduce your message size" in low or "413" in low:
        return "Video dilimi modele sığmadı. Daha kısa bir bölümle tekrar dene."
    if "bu anahtarda yok" in low or "model yok" in low or "model_not_found" in low:
        return "Analiz ayarı güncelleniyor. Biraz sonra tekrar dene."
    if "altyazı" in low:
        return text[:280]
    return text[:280]


def _analyze_with_lines(
    *,
    lines: list[dict],
    user_id: str,
    video_id: str,
    canonical_url: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_meta: dict,
    cache_key: str,
    extra_keys: tuple,
    reservation,
    db: Session,
    job_id: str | None = None,
    focus_start: int = 0,
    focus_bucket: int = 0,
) -> AnalyzeResponse:
    from app.services import rag as rag_service
    from app.services import analyze_jobs as jobs

    jobs.raise_if_cancelled(job_id)
    if not lines:
        raise ValueError("Bu video için altyazı bulunamadı.")
    mismatch = transcript_off_subject(lines, subject)
    if mismatch:
        raise ValueError(mismatch)
    from app.services.llm import reset_analyze_provider_chain

    reset_analyze_provider_chain()
    slices = slice_transcript(lines, SLICE_SECONDS)
    if not slices:
        raise ValueError("Bu video için altyazı bulunamadı.")
    first, remaining_slices = pick_content_slice(slices, prefer_start=focus_start)
    candidates = [first, *remaining_slices]
    llm_data = None
    chosen_idx = 0
    last_err: BaseException | None = None
    # Tek LLM çağrısı: 1-2 komşu dilimi birleştir → daha detaylı not, ek fatura yok.
    from app.services.youtube import slice_promo_ratio

    primary = candidates[0]
    block = str(primary.get("block") or "")
    label = str(primary.get("label") or "")
    if len(candidates) > 1:
        nxt = candidates[1]
        if slice_promo_ratio(str(nxt.get("block") or "")) < 0.22:
            merged = (block + "\n" + str(nxt.get("block") or "")).strip()
            if len(merged) > len(block):
                block = merged
                label = f"{label} + {nxt.get('label') or ''}".strip(" +")
    jobs.raise_if_cancelled(job_id)
    # LLM bitmeden önce sadece kaliteli erken not bas (sohbet çöpü yok).
    if job_id:
        try:
            early = quick_transcript_notes(block[:5000], subject)
            early_notes = _pack_notes(early.get("notes"), video_id)
            if early_notes:
                early_overlay: dict = {}
                try:
                    snap0 = jobs.snapshot(job_id)
                    if snap0:
                        early_overlay = dict(snap0.get("overlay") or {})
                except Exception:
                    early_overlay = {}
                jobs.set_progress(
                    job_id,
                    notes=[item.model_dump() for item in early_notes],
                    questions=[],
                    persona={"catchphrases": [], "tone": "öğretici, net"},
                    chunks_done=0,
                    status="running",
                    chunks_total=1,
                    overlay=early_overlay,
                )
        except Exception:
            logger.exception("Erken not basımı atlandı")
    last_err: BaseException | None = None
    try:
        llm_data = analyze_slice(
            block,
            subject,
            min(6, max(4, question_count)),
            exam_target,
            subject_meta["subject_type"],
            subject_meta["is_yks_fen_question"],
            "",
            window_label=label,
            note_count=6,
        )
        chosen_idx = 0
        first = primary
    except Exception as exc:  # noqa: BLE001 — fallback slice dene
        last_err = exc
        llm_data = None
        for idx, piece in enumerate(candidates[1:3], start=1):
            jobs.raise_if_cancelled(job_id)
            try:
                llm_data = analyze_slice(
                    piece["block"],
                    subject,
                    min(6, max(4, question_count)),
                    exam_target,
                    subject_meta["subject_type"],
                    subject_meta["is_yks_fen_question"],
                    "",
                    window_label=piece["label"],
                    note_count=6,
                )
                chosen_idx = idx
                first = piece
                break
            except Exception as inner:  # noqa: BLE001
                last_err = inner
                continue
    if llm_data is None:
        # Son çare: altyazı notu — mümkün olduğunca boş hata verme
        llm_data = quick_transcript_notes(block[:5000], subject)
        if not (llm_data.get("notes") or []):
            llm_data = quick_transcript_notes(
                "\n".join(str(c.get("block") or "") for c in candidates[:3])[:6000],
                subject,
            )
        if not (llm_data.get("notes") or []):
            raise last_err or RuntimeError(
                "Bu videoda yeterli altyazı bulunamadı. Altyazılı bir video dene."
            )
        chosen_idx = 0
        first = primary
    jobs.raise_if_cancelled(job_id)
    remaining_slices = candidates[chosen_idx + 1 :]
    try:
        rag_service.ingest_video_signals(
            db,
            user_id=user_id,
            video_id=video_id,
            lines=lines,
            subject=subject,
            exam_target=exam_target,
        )
    except Exception:
        db.rollback()

    notes = _pack_notes(
        llm_data.get("notes"),
        video_id,
        time_offset=int(first.get("start") or 0),
    )
    # Çöp / kota uyarısı notlarını UI'ya verme
    notes = [
        n
        for n in notes
        if n.title.strip()
        and n.text.strip()
        and "hourly limit" not in (n.text + n.exam_tip).lower()
        and "cannot provide" not in (n.text + n.exam_tip).lower()
        and "knowledge base" not in (n.text + n.exam_tip).lower()
    ]
    questions = _pack_questions(
        llm_data.get("questions"),
        video_id,
        time_offset=int(first.get("start") or 0),
    )
    # Offset sonrası gerçek dakika; uzun videoda >=600 filtresi notları silmesin.
    if focus_start > 0:
        floor = max(0, int(focus_start) - 120)
        filtered_notes = [n for n in notes if int(n.timestamp or 0) >= floor]
        filtered_qs = [q for q in questions if int(q.timestamp or 0) >= floor]
        if filtered_notes:
            notes = filtered_notes
        if filtered_qs:
            questions = filtered_qs
    if notes or questions:
        reservation = credit_service.confirm(db, user_id, video_id, reservation)
    else:
        reservation = credit_service.refund(db, user_id, reservation)
    overlay = credit_service.overlay(reservation)

    # 30 dk video: ilk dilim + en fazla 4 dilim daha (arka planda eklenir).
    remaining = list(remaining_slices[:4])
    total_chunks = 1 + len(remaining)
    if not job_id:
        job_id = jobs.create_job(
            user_id=user_id,
            video_id=video_id,
            video_url=canonical_url,
            subject=subject,
            chunks_total=total_chunks,
            overlay=overlay,
            focus_bucket=focus_bucket,
        )
    persona = ai_engine.parse_persona(llm_data.get("teacher_persona")).model_dump()
    done = 1
    status = "running" if remaining else "done"
    jobs.set_progress(
        job_id,
        notes=[item.model_dump() for item in notes],
        questions=[item.model_dump() for item in questions],
        persona=persona,
        chunks_done=done,
        status=status,
        chunks_total=total_chunks,
        overlay=overlay,
    )
    _persist_notebook(
        user_id=user_id,
        subject=subject,
        video_id=video_id,
        video_url=canonical_url,
        notes=notes,
        questions=questions,
        persona=persona,
        exam_target=exam_target,
        db=db,
    )
    if remaining:
        if notes:
            dump = AnalyzeResponse(
                video_id=video_id,
                video_url=canonical_url,
                subject=subject,
                notes=notes,
                questions=questions,
                teacher_persona=persona,
                job_id=job_id,
                job_status="running",
                chunks_done=done,
                chunks_total=total_chunks,
                **overlay,
            ).model_dump()
            dump["analyze_span"] = "partial"
            dump["llm_model"] = settings.active_model
            dump["notes_depth"] = 6
            dump["focus_bucket"] = int(focus_bucket or 0)
            dump["focus_start"] = int(focus_start or 0)
            dump["exam_target"] = exam_target or ""
            for key in extra_keys:
                dump.pop(key, None)
            cache.save(cache_key, dump)
        threading.Thread(
            target=_continue_analyze_job,
            args=(
                job_id,
                remaining,
                user_id,
                subject,
                exam_target,
                subject_meta["subject_type"],
                subject_meta["is_yks_fen_question"],
                video_id,
                cache_key,
                extra_keys,
            ),
            daemon=True,
            name=f"analyze-cont-{job_id}",
        ).start()
    elif notes:
        dump = AnalyzeResponse(
            video_id=video_id,
            video_url=canonical_url,
            subject=subject,
            notes=notes,
            questions=questions,
            teacher_persona=persona,
            job_id=job_id,
            job_status="done",
            chunks_done=1,
            chunks_total=1,
            **overlay,
        ).model_dump()
        dump["analyze_span"] = "full"
        dump["llm_model"] = settings.active_model
        dump["notes_depth"] = 6
        dump["focus_bucket"] = int(focus_bucket or 0)
        dump["focus_start"] = int(focus_start or 0)
        dump["exam_target"] = exam_target or ""
        for key in extra_keys:
            dump.pop(key, None)
        cache.save(cache_key, dump)
    return AnalyzeResponse(
        video_id=video_id,
        video_url=canonical_url,
        subject=subject,
        notes=notes,
        questions=questions,
        teacher_persona=persona,
        job_id=job_id,
        job_status=status,
        chunks_done=done,
        chunks_total=total_chunks,
        **overlay,
    )


def _analyze_lines_job(
    job_id: str,
    lines: list[dict],
    user_id: str,
    video_id: str,
    canonical_url: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_meta: dict,
    cache_key: str,
    extra_keys: tuple,
    reservation,
    focus_start: int = 0,
    focus_bucket: int = 0,
) -> None:
    """Altyazı hazırken LLM'i HTTP dışında çalıştır — tarayıcı timeout olmasın."""
    from app.database.session import SessionLocal
    from app.services import analyze_jobs as jobs

    db = SessionLocal()
    try:
        _analyze_with_lines(
            lines=lines,
            user_id=user_id,
            video_id=video_id,
            canonical_url=canonical_url,
            subject=subject,
            question_count=question_count,
            exam_target=exam_target,
            subject_meta=subject_meta,
            cache_key=cache_key,
            extra_keys=extra_keys,
            reservation=reservation,
            db=db,
            job_id=job_id,
            focus_start=focus_start,
            focus_bucket=focus_bucket,
        )
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.confirm_charged(db, follower_id, video_id, kind)
            except Exception:
                logger.exception("Takipçi confirm başarısız %s", follower_id)
    except jobs.JobCancelled:
        logger.info("Analiz iptal %s", job_id)
        try:
            credit_service.refund(db, user_id, reservation)
        except Exception:
            logger.exception("İptal iadesi başarısız %s", job_id)
        jobs.finish(job_id, "error", error="Analiz iptal edildi.")
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.refund_charged(db, follower_id, kind)
            except Exception:
                logger.exception("Takipçi iadesi başarısız %s", follower_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Arka plan analiz %s başarısız: %s", job_id, exc)
        try:
            credit_service.refund(db, user_id, reservation)
        except Exception:
            logger.exception("Analiz iadesi başarısız %s", job_id)
        jobs.finish(job_id, "error", error=_public_analyze_error(exc))
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.refund_charged(db, follower_id, kind)
            except Exception:
                logger.exception("Takipçi iadesi başarısız %s", follower_id)
    finally:
        release_work(video_id, subject, focus_bucket)
        db.close()


def _fetch_then_analyze_job(
    job_id: str,
    user_id: str,
    video_id: str,
    canonical_url: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None,
    subject_meta: dict,
    cache_key: str,
    extra_keys: tuple,
    reservation,
    focus_start: int = 0,
    focus_bucket: int = 0,
) -> None:
    from app.database.session import SessionLocal
    from app.services import analyze_jobs as jobs

    db = SessionLocal()
    try:
        jobs.raise_if_cancelled(job_id)
        lines = fetch_transcript_lines(video_id, subject=subject)
        if not lines:
            raise ValueError("Bu video için altyazı bulunamadı.")
        jobs.raise_if_cancelled(job_id)
        user = penalty_service.get_or_create_user(db, user_id)
        if credit_service.is_ad_tier(user) and not credit_service.already_converted(
            db, user_id, video_id
        ):
            credit_service.enforce_duration(
                user, transcript_duration_seconds(lines), db
            )
        _analyze_with_lines(
            lines=lines,
            user_id=user_id,
            video_id=video_id,
            canonical_url=canonical_url,
            subject=subject,
            question_count=question_count,
            exam_target=exam_target,
            subject_meta=subject_meta,
            cache_key=cache_key,
            extra_keys=extra_keys,
            reservation=reservation,
            db=db,
            job_id=job_id,
            focus_start=focus_start,
            focus_bucket=focus_bucket,
        )
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.confirm_charged(db, follower_id, video_id, kind)
            except Exception:
                logger.exception("Takipçi confirm başarısız %s", follower_id)
    except jobs.JobCancelled:
        logger.info("Analiz iptal %s", job_id)
        try:
            credit_service.refund(db, user_id, reservation)
        except Exception:
            logger.exception("İptal iadesi başarısız %s", job_id)
        jobs.finish(job_id, "error", error="Analiz iptal edildi.")
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.refund_charged(db, follower_id, kind)
            except Exception:
                logger.exception("Takipçi iadesi başarısız %s", follower_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Arka plan analiz %s başarısız: %s", job_id, exc)
        try:
            credit_service.refund(db, user_id, reservation)
        except Exception:
            logger.exception("Analiz iadesi başarısız %s", job_id)
        jobs.finish(job_id, "error", error=_public_analyze_error(exc))
        for follower_id, kind in jobs.take_unsettled_followers(job_id):
            try:
                credit_service.refund_charged(db, follower_id, kind)
            except Exception:
                logger.exception("Takipçi iadesi başarısız %s", follower_id)
    finally:
        release_work(video_id, subject, focus_bucket)
        db.close()


def _continue_analyze_job(
    job_id: str,
    remaining: list[dict],
    user_id: str,
    subject: str | None,
    exam_target: str | None,
    subject_type: str | None,
    is_yks_fen_question: bool,
    video_id: str,
    cache_key: str,
    extra_keys: tuple,
) -> None:
    from app.services import analyze_jobs as jobs

    snap = jobs.snapshot(job_id)
    if not snap:
        return
    notes = [NoteItem.model_validate(item) for item in snap["notes"]]
    questions = [QuestionItem.model_validate(item) for item in snap["questions"]]
    personas = [snap.get("teacher_persona")]
    done = int(snap.get("chunks_done") or 1)
    for piece in remaining:
        if jobs.is_cancel_requested(job_id):
            jobs.finish(job_id, "error", error="Analiz iptal edildi.")
            return
        try:
            llm_data = analyze_slice(
                piece["block"],
                subject,
                5,
                exam_target,
                subject_type,
                is_yks_fen_question,
                "",
                window_label=piece.get("label") or "",
                note_count=5,
            )
        except Exception as exc:
            logger.warning("Dilim atlandı %s: %s", piece.get("label"), exc)
            jobs.set_progress(
                job_id,
                notes=[item.model_dump() for item in notes],
                questions=[item.model_dump() for item in questions],
                persona=snap.get("teacher_persona") or {},
                chunks_done=done,
            )
            continue
        done += 1
        offset = int(piece.get("start") or 0)
        more_notes = _pack_notes(
            llm_data.get("notes"),
            video_id,
            start=len(notes) + 1,
            time_offset=offset,
        )
        more_notes = [
            n
            for n in more_notes
            if n.title.strip()
            and n.text.strip()
            and "hourly limit" not in (n.text + n.exam_tip).lower()
            and "cannot provide" not in (n.text + n.exam_tip).lower()
            and "knowledge base" not in (n.text + n.exam_tip).lower()
        ]
        if not more_notes:
            logger.warning("Dilim notları çöp/boş atlandı: %s", piece.get("label"))
            jobs.set_progress(
                job_id,
                notes=[item.model_dump() for item in notes],
                questions=[item.model_dump() for item in questions],
                persona=snap.get("teacher_persona") or {},
                chunks_done=done,
            )
            continue
        notes.extend(more_notes)
        questions.extend(
            _pack_questions(
                llm_data.get("questions"),
                video_id,
                start=len(questions) + 1,
                time_offset=offset,
            )
        )
        if llm_data.get("teacher_persona"):
            personas.append(llm_data.get("teacher_persona"))
        persona = ai_engine.merge_personas(personas).model_dump()
        jobs.set_progress(
            job_id,
            notes=[item.model_dump() for item in notes],
            questions=[item.model_dump() for item in questions],
            persona=persona,
            chunks_done=done,
        )
        _persist_notebook(
            user_id=user_id,
            subject=subject,
            video_id=video_id,
            video_url=str(snap.get("video_url") or ""),
            notes=notes,
            questions=questions,
            persona=persona,
            exam_target=exam_target,
        )
    jobs.finish(job_id, "done")
    for follower_id, kind in jobs.take_unsettled_followers(job_id):
        try:
            from app.database.session import SessionLocal

            settle = SessionLocal()
            try:
                credit_service.confirm_charged(settle, follower_id, video_id, kind)
            finally:
                settle.close()
        except Exception:
            logger.exception("Takipçi confirm başarısız %s", follower_id)
    final = jobs.snapshot(job_id)
    if not final or not final.get("notes"):
        return
    dump = {
        "video_id": final["video_id"],
        "video_url": final["video_url"],
        "subject": final.get("subject") or None,
        "notes": final["notes"],
        "questions": final.get("questions") or [],
        "teacher_persona": final["teacher_persona"],
        "cached": False,
        "analyze_span": "full",
        "llm_model": settings.active_model,
        "notes_depth": 6,
        "focus_bucket": int(final.get("focus_bucket") or 0),
        "exam_target": exam_target or "",
        "job_id": "",
        "job_status": "done",
        "chunks_done": final["chunks_total"],
        "chunks_total": final["chunks_total"],
    }
    for key in extra_keys:
        dump.pop(key, None)
    cache.save(cache_key, dump)


def _to_note(
    item: dict, index: int, video_id: str, time_offset: int = 0
) -> NoteItem:
    if not isinstance(item, dict):
        raise TypeError("not bir nesne değil")
    seconds = max(0, int(float(item.get("timestamp") or 0)) + int(time_offset or 0))
    detail = item.get("detail") or item.get("text") or ""
    raw_points = item.get("key_points") or []
    if not isinstance(raw_points, list):
        raw_points = [raw_points]
    points = [str(p).strip() for p in raw_points if str(p).strip()]
    return NoteItem(
        id=f"note_{index}",
        title=str(item.get("title") or "").strip(),
        text=str(detail).strip(),
        key_points=points,
        mnemonic=str(item.get("mnemonic") or "").strip(),
        exam_tip=str(item.get("exam_tip") or "").strip(),
        timestamp=seconds,
        timestamp_label=format_timestamp_label(seconds),
        video_url_with_t=build_watch_url(video_id, seconds),
    )


def _to_question(
    item: dict, index: int, video_id: str, time_offset: int = 0
) -> QuestionItem:
    from app.services.subjects import parse_premises, parse_steps

    if not isinstance(item, dict):
        raise TypeError("soru bir nesne değil")
    seconds = max(0, int(float(item.get("timestamp") or 0)) + int(time_offset or 0))
    options = item.get("options") or {}
    if isinstance(options, list):
        options = {
            letter: str(val)
            for letter, val in zip("ABCDE", options)
            if str(val).strip()
        }
    elif not isinstance(options, dict):
        options = {}
    return QuestionItem(
        id=f"q_{index}",
        text=str(item.get("text") or "").strip(),
        options={str(k): str(v) for k, v in options.items()},
        correct=str(item.get("correct") or "").strip().upper()[:1],
        explanation=str(item.get("explanation") or "").strip(),
        trap_explanation=str(
            item.get("trap_explanation") or item.get("explanation") or ""
        ).strip(),
        topic=str(item.get("topic") or "").strip(),
        difficulty=str(item.get("difficulty") or "").strip().lower(),
        timestamp=seconds,
        timestamp_label=format_timestamp_label(seconds),
        video_url_with_t=build_watch_url(video_id, seconds),
        subject_type=str(item.get("subject_type") or "sozel"),
        is_yks_fen_question=bool(item.get("is_yks_fen_question") or item.get("is_yks_fen")),
        fen_branch=str(item.get("fen_branch") or ""),
        misconception_tag=str(item.get("misconception_tag") or ""),
        step_by_step_solution=parse_steps(item.get("step_by_step_solution")),
        shortcut_tactic=str(item.get("shortcut_tactic") or "").strip(),
        premises=parse_premises(item.get("premises")),
    )
