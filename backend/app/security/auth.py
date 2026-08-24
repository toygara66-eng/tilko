"""JWT, bcrypt ve istek kimliği — savunma katmanı."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.services.penalty import get_or_create_user

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
USER_RE = re.compile(r"^[A-Za-z0-9_\-.]{3,64}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/login",
    "/auth/register",
    "/auth/google",
    "/login",
    "/subscription/webhook",
}
PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi", "/captions")
ALGORITHM = "HS256"
VALID_EXAMS = {
    "kpss_lisans",
    "kpss_onlisans",
    "kpss_ortaogretim",
    "yks",
    "oabt",
    "lgs",
    "other",
}


def hash_password(plain: str) -> str:
    secret = (plain or "").encode("utf-8")[:72].decode("utf-8", errors="ignore")
    if len(secret) < 8:
        raise ValueError("Şifre en az 8 karakter olmalı.")
    return pwd_context.hash(secret)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    secret = (plain or "").encode("utf-8")[:72].decode("utf-8", errors="ignore")
    try:
        return bool(pwd_context.verify(secret, hashed))
    except Exception:  # noqa: BLE001
        return False


def create_token(user_id: str, role: str = "student") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": user_id, "role": role or "student", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Oturum süresi doldu. Yeniden giriş yap.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Geçersiz oturum. Bearer token gerekli.") from exc
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Geçersiz oturum.")
    return user_id


def bearer_from(request: Request) -> str:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer token gerekli.")
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization: Bearer token gerekli.")
    return decode_token(token)


def is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def play_webhook_ok(request: Request) -> bool:
    from hmac import compare_digest

    expected = (settings.play_webhook_secret or "").strip()
    if not expected:
        return False
    got = (request.headers.get("X-Play-Webhook-Secret") or "").strip()
    if not got or len(got) != len(expected):
        return False
    return compare_digest(got, expected)


def admin_ok(request: Request) -> bool:
    from hmac import compare_digest

    expected = (settings.admin_api_secret or "").strip()
    if not expected:
        return False
    got = (request.headers.get("X-Admin-Secret") or "").strip()
    if not got or len(got) != len(expected):
        return False
    return compare_digest(got, expected)


def actor(request: Request) -> str:
    uid = getattr(request.state, "user_id", "") or ""
    if not uid:
        uid = bearer_from(request)
        request.state.user_id = uid
    return uid


def normalize_email(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return ""
    if not EMAIL_RE.match(value) or len(value) > 256:
        raise ValueError("Geçerli bir e-posta adresi gir.")
    return value


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D+", "", (raw or "").strip())
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "90" + digits
    elif len(digits) == 12 and digits.startswith("90"):
        pass
    else:
        raise ValueError("Telefon 05xx… veya +90 5xx… formatında olmalı.")
    if not (len(digits) == 12 and digits.startswith("905")):
        raise ValueError("Türkiye cep telefonu numarası gir (05xx…).")
    return digits


def _normalize_user_id(raw: str) -> str:
    value = (raw or "").strip()
    if not USER_RE.match(value):
        raise ValueError("Kullanıcı adı 3-64 karakter, harf/rakam olmalı.")
    return value


def _normalize_exam(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return ""
    if value not in VALID_EXAMS:
        raise ValueError("Sınav hedefi geçersiz (KPSS / YKS / ÖABT / LGS).")
    return value


def _uid_from_email(email: str) -> str:
    local = re.sub(r"[^a-z0-9]", "", email.split("@", 1)[0].lower())[:18] or "mail"
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:8]
    uid = f"{local}_{digest}"
    return uid[:64]


def _uid_from_phone(phone: str) -> str:
    return f"p_{phone}"[:64]


def _auth_view(db: Session, user) -> dict:
    from app.services.teacher import dashboard_for, display_name_of, normalize_role

    role = normalize_role(getattr(user, "role", "") or "student")
    return {
        "access_token": create_token(user.user_id, role),
        "token_type": "bearer",
        "user_id": user.user_id,
        "role": role,
        "display_name": display_name_of(db, user.user_id),
        "dashboard": dashboard_for(role),
    }


def _stamp_teacher(user, display_name: str) -> None:
    user.role = "teacher"
    user.is_onboarded = True
    user.is_tested = True
    if display_name:
        user.display_name = display_name[:64]


def _apply_exam(user, exam_target: str) -> None:
    exam = _normalize_exam(exam_target)
    if not exam:
        return
    user.exam_target = exam
    user.is_onboarded = True


def find_user_by_login(db: Session, identifier: str):
    from app.database.models import User

    raw = (identifier or "").strip()
    if not raw:
        return None
    if USER_RE.match(raw):
        user = db.get(User, raw)
        if user is not None:
            return user
    try:
        email = normalize_email(raw) if "@" in raw else ""
    except ValueError:
        email = ""
    if email:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user is not None:
            return user
    try:
        phone = normalize_phone(raw)
    except ValueError:
        phone = ""
    if phone:
        return db.scalars(select(User).where(User.phone == phone)).first()
    return None


def register_user(
    db: Session,
    user_id: str = "",
    password: str = "",
    role: str = "student",
    display_name: str = "",
    *,
    email: str = "",
    phone: str = "",
    exam_target: str = "",
) -> dict:
    from app.database.models import User
    from app.services.teacher import normalize_role, set_display_name

    intended = normalize_role(role, default="student")
    if intended == "teacher" and settings.is_production:
        raise ValueError("Hoca hesabı buradan açılamaz.")

    name = (display_name or "").strip()
    if intended == "student" and len(name) < 2:
        raise ValueError("Ad soyad gerekli.")

    mail = normalize_email(email) if (email or "").strip() else ""
    tel = normalize_phone(phone) if (phone or "").strip() else ""
    uid_raw = (user_id or "").strip()

    if not mail and not tel and not uid_raw:
        raise ValueError("E-posta, telefon veya kullanıcı adı gerekli.")

    if mail:
        clash = db.scalars(select(User).where(User.email == mail)).first()
        if clash is not None and (clash.password_hash or "").strip():
            raise ValueError("Bu e-posta zaten kayıtlı. Giriş yap.")
    if tel:
        clash = db.scalars(select(User).where(User.phone == tel)).first()
        if clash is not None and (clash.password_hash or "").strip():
            raise ValueError("Bu telefon zaten kayıtlı. Giriş yap.")

    if uid_raw:
        uid = _normalize_user_id(uid_raw)
    elif mail:
        uid = _uid_from_email(mail)
    else:
        uid = _uid_from_phone(tel)

    existing = db.get(User, uid)
    if existing is not None and (existing.password_hash or "").strip():
        raise ValueError("Bu kullanıcı zaten kayıtlı. Giriş yap.")

    hashed = hash_password(password)
    user = existing or get_or_create_user(db, uid)
    user.password_hash = hashed
    if mail:
        user.email = mail
    if tel:
        user.phone = tel
    if intended == "teacher":
        _stamp_teacher(user, name)
    else:
        user.role = "student"
        user.display_name = name[:64]
        _apply_exam(user, exam_target)
        if not (user.exam_target or "").strip():
            raise ValueError("KPSS / YKS / sınav hedefi seç.")
    db.add(user)
    db.commit()
    if name:
        set_display_name(db, uid, name)
        db.commit()
    db.refresh(user)
    return _auth_view(db, user)


def login_user(
    db: Session,
    user_id: str = "",
    password: str = "",
    role: str = "",
    display_name: str = "",
    *,
    email: str = "",
    phone: str = "",
) -> dict:
    from app.services.teacher import normalize_role, set_display_name

    identifier = (
        (email or "").strip()
        or (phone or "").strip()
        or (user_id or "").strip()
    )
    if not identifier:
        raise ValueError("E-posta, telefon veya kullanıcı adı gerekli.")
    user = find_user_by_login(db, identifier)
    stored = (getattr(user, "password_hash", None) or "").strip() if user else ""
    if user is None or not stored or not verify_password(password, stored):
        raise ValueError("E-posta/telefon veya şifre hatalı.")
    intended = (role or "").strip().lower()
    actual = normalize_role(getattr(user, "role", "") or "student")
    if intended == "teacher" and actual not in {"teacher", "admin"}:
        raise ValueError("Bu hesap öğrenci hesabı. Hoca paneli için hoca girişi kullan.")
    if intended == "student" and actual in {"teacher", "admin"}:
        raise ValueError("Bu bir hoca hesabı. Hoca Girişi ile devam et.")
    if intended == "teacher" and actual in {"teacher", "admin"} and (display_name or "").strip():
        set_display_name(db, user.user_id, display_name)
        db.commit()
        db.refresh(user)
    return _auth_view(db, user)


def _google_audiences() -> list[str]:
    ids = [
        (settings.google_client_id or "").strip(),
        (settings.google_android_client_id or "").strip(),
    ]
    return [item for item in ids if item]


def verify_google_id_token(id_token: str) -> dict:
    """Google ID token doğrula (GIS / Android)."""
    token = (id_token or "").strip()
    if not token:
        raise ValueError("Google jetonu eksik.")
    audiences = _google_audiences()
    if not audiences:
        raise ValueError("GOOGLE_CLIENT_ID sunucuda ayarlı değil.")
    import httpx

    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token},
        )
    if response.status_code != 200:
        raise ValueError("Google jetonu geçersiz veya süresi dolmuş.")
    data = response.json()
    aud = str(data.get("aud") or "").strip()
    if aud not in audiences:
        raise ValueError("Google istemci kimliği uyuşmuyor.")
    if str(data.get("email_verified") or "").lower() not in {"true", "1"}:
        if not data.get("email"):
            raise ValueError("Google e-posta doğrulanmamış.")
    sub = str(data.get("sub") or "").strip()
    if not sub:
        raise ValueError("Google kimliği okunamadı.")
    return data


def login_with_google(
    db: Session,
    id_token: str,
    *,
    role: str = "",
    display_name: str = "",
    exam_target: str = "",
    link_user_id: str = "",
) -> dict:
    from app.database.models import User
    from app.services.teacher import normalize_role, set_display_name

    claims = verify_google_id_token(id_token)
    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip()[:256].lower()
    name = (display_name or claims.get("name") or "").strip()[:64]
    intended = normalize_role(role, default="student")
    if intended == "teacher" and settings.is_production:
        raise ValueError("Hoca hesabı Google ile buradan açılamaz.")

    user = db.scalars(select(User).where(User.google_sub == sub)).first()
    if user is None and email:
        user = db.scalars(select(User).where(User.email == email)).first()

    link = (link_user_id or "").strip()
    if user is None and link.startswith("aday-"):
        guest = db.get(User, link)
        if guest is not None and not (getattr(guest, "google_sub", "") or "").strip():
            user = guest

    if user is None:
        uid = f"g_{sub}"[:64]
        if not USER_RE.match(uid):
            uid = f"g{sub}"[:64]
        user = get_or_create_user(db, uid)

    user.google_sub = sub
    if email:
        user.email = email
    if intended == "teacher":
        _stamp_teacher(user, name)
    elif not (getattr(user, "role", "") or "").strip() or user.role == "student":
        user.role = "student"
    if name:
        user.display_name = name
    _apply_exam(user, exam_target)
    db.add(user)
    db.commit()
    if name:
        set_display_name(db, user.user_id, name)
        db.commit()
    db.refresh(user)
    return _auth_view(db, user)


def auth_error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def _path_claimed_user(path: str) -> str | None:
    parts = [item for item in path.split("/") if item]
    if len(parts) >= 2 and parts[0] in {"progress", "traps", "daily_missions", "notebook"}:
        return parts[1]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "penalty":
        if parts[2] in {"answer"}:
            return None
        return parts[2]
    return None


async def jwt_guard(request: Request, call_next):
    if request.method == "OPTIONS" or is_public(request.url.path):
        return await call_next(request)
    if request.url.path == "/subscription/verify" and play_webhook_ok(request):
        request.state.play_webhook = True
        return await call_next(request)
    if (
        request.url.path.startswith("/admin/")
        or request.url.path.startswith("/bulletin")
        or request.url.path == "/api/prizes/settle"
    ):
        if not admin_ok(request):
            return auth_error(401, "Admin anahtarı geçersiz.")
        request.state.admin = True
        try:
            request.state.user_id = bearer_from(request)
        except HTTPException:
            request.state.user_id = "admin"
        return await call_next(request)
    try:
        uid = bearer_from(request)
    except HTTPException as exc:
        return auth_error(exc.status_code, str(exc.detail))
    request.state.user_id = uid

    claimed_query = request.query_params.get("user_id")
    if claimed_query and claimed_query != uid:
        return auth_error(403, "Kimlik uyuşmuyor.")
    claimed_path = _path_claimed_user(request.url.path)
    if claimed_path and claimed_path != uid:
        return auth_error(403, "Kimlik uyuşmuyor.")

    content_type = (request.headers.get("content-type") or "").lower()
    if request.method in {"POST", "PUT", "PATCH"} and "application/json" in content_type:
        body = await request.body()
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict) and "user_id" in data:
                claimed = str(data.get("user_id") or "").strip()
                if claimed and claimed != uid:
                    return auth_error(403, "Kimlik uyuşmuyor.")
                data["user_id"] = uid
                body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                request.scope["headers"] = [
                    (key, value)
                    if key != b"content-length"
                    else (key, str(len(body)).encode("ascii"))
                    for key, value in request.scope.get("headers") or []
                ]

        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

    return await call_next(request)
