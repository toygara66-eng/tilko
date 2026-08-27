"""E-posta doğrulama — kayıt sonrası 6 haneli kod (Resend)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import PasswordReset, User
from app.security.auth import (
    _auth_view,
    find_user_by_login,
    normalize_email,
)

logger = logging.getLogger(__name__)
CODE_TTL_MINUTES = 30
CODE_LENGTH = 6
PURPOSE = "verify"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str, user_id: str) -> str:
    raw = f"{PURPOSE}:{code}:{user_id}:{settings.jwt_secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _make_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def _hint(email: str) -> str:
    parts = (email or "").split("@")
    if len(parts) != 2:
        return "***"
    return f"{parts[0][:2]}***@{parts[1]}"


def _send_verify_email(to_email: str, code: str, display_name: str) -> bool:
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        return False
    from_addr = (settings.resend_from_email or "").strip() or "Tilko <onboarding@resend.dev>"
    name = (display_name or "").strip() or "Tilko kullanıcısı"
    subject = "Tilko e-posta doğrulama kodu"
    text = (
        f"Merhaba {name},\n\n"
        f"Tilko hesabını doğrulamak için kodun: {code}\n"
        f"Kod {CODE_TTL_MINUTES} dakika geçerli.\n\n"
        f"Bu isteği sen yapmadıysan yok say.\n"
        f"— Tilko\n"
        f"{settings.public_app_url}/giris\n"
    )
    html = (
        f"<p>Merhaba <strong>{name}</strong>,</p>"
        f"<p>Tilko hesabını doğrulamak için kodun:</p>"
        f"<p style='font-size:28px;letter-spacing:6px;font-weight:700'>{code}</p>"
        f"<p>Kod {CODE_TTL_MINUTES} dakika geçerli.</p>"
        f"<p>Bu isteği sen yapmadıysan yok say.</p>"
        f"<p>— Tilko</p>"
    )
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_addr,
                "to": [to_email],
                "subject": subject,
                "text": text,
                "html": html,
            },
            timeout=20.0,
        )
        if response.status_code >= 300:
            logger.warning("Resend verify hata %s: %s", response.status_code, response.text[:300])
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Doğrulama e-postası gönderilemedi")
        return False


def issue_verification_code(db: Session, user: User) -> dict:
    """Yeni doğrulama kodu üretir ve e-posta gönderir."""
    mail = (user.email or "").strip().lower()
    if not mail:
        raise ValueError("Doğrulama için e-posta gerekli.")
    if bool(getattr(user, "email_verified", True)):
        return {
            "ok": True,
            "sent": False,
            "already_verified": True,
            "destination_hint": _hint(mail),
            "message": "E-posta zaten doğrulanmış. Giriş yapabilirsin.",
            "debug_code": "",
        }

    code = _make_code()
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.user_id)
        .where(PasswordReset.purpose == PURPOSE)
        .where(PasswordReset.used.is_(False))
        .values(used=True)
    )
    row = PasswordReset(
        user_id=user.user_id,
        code_hash=_hash_code(code, user.user_id),
        channel="email",
        purpose=PURPOSE,
        destination=mail,
        expires_at=_utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
        used=False,
    )
    db.add(row)
    db.commit()

    sent = _send_verify_email(mail, code, user.display_name or "")
    hint = _hint(mail)
    out = {
        "ok": True,
        "sent": sent,
        "already_verified": False,
        "destination_hint": hint,
        "message": "",
        "debug_code": "",
    }
    if sent:
        out["message"] = (
            f"Doğrulama kodu {hint} adresine gönderildi. "
            f"{CODE_TTL_MINUTES} dakika geçerli. Spam klasörüne de bak."
        )
    elif not (settings.resend_api_key or "").strip():
        out["message"] = (
            "Doğrulama e-postası henüz yapılandırılmamış. "
            "Geliştirme ortamında kod aşağıda gösterilir."
        )
        if not settings.is_production:
            out["debug_code"] = code
            out["message"] += f" Kod: {code}"
    else:
        out["message"] = (
            "Kod oluşturuldu ama e-posta gönderilemedi. Spam’i kontrol et; "
            "gelmezse ‘Kodu tekrar gönder’e bas."
        )
        if not settings.is_production:
            out["debug_code"] = code
    return out


def resend_verification(db: Session, *, email: str) -> dict:
    mail = normalize_email(email) if (email or "").strip() else ""
    if not mail:
        raise ValueError("E-posta gerekli.")
    user = find_user_by_login(db, mail)
    generic = {
        "ok": True,
        "sent": False,
        "already_verified": False,
        "destination_hint": _hint(mail),
        "message": (
            "Kayıtlı bir hesap varsa doğrulama kodu gönderildi. "
            "Birkaç dakika içinde gelmezse spam klasörüne bak."
        ),
        "debug_code": "",
    }
    if user is None:
        return generic
    if bool(getattr(user, "email_verified", True)):
        return {
            **generic,
            "already_verified": True,
            "message": "E-posta zaten doğrulanmış. Giriş yapabilirsin.",
        }
    if not (user.email or "").strip():
        user.email = mail
        db.add(user)
        db.commit()
    return issue_verification_code(db, user)


def verify_email_code(db: Session, *, email: str, code: str) -> dict:
    mail = normalize_email(email) if (email or "").strip() else ""
    if not mail:
        raise ValueError("E-posta gerekli.")
    pin = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(pin) != CODE_LENGTH:
        raise ValueError(f"{CODE_LENGTH} haneli kodu gir.")

    user = find_user_by_login(db, mail)
    if user is None:
        raise ValueError("Kod geçersiz veya süresi dolmuş.")
    if bool(getattr(user, "email_verified", False)):
        return _auth_view(db, user)

    now = _utcnow()
    rows = list(
        db.scalars(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.user_id)
            .where(PasswordReset.purpose == PURPOSE)
            .where(PasswordReset.used.is_(False))
            .order_by(PasswordReset.created_at.desc())
            .limit(5)
        ).all()
    )
    match: PasswordReset | None = None
    for row in rows:
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            continue
        if secrets.compare_digest(row.code_hash, _hash_code(pin, user.user_id)):
            match = row
            break
    if match is None:
        raise ValueError("Kod geçersiz veya süresi dolmuş.")

    user.email_verified = True
    if not (user.email or "").strip():
        user.email = mail
    match.used = True
    db.add(user)
    db.add(match)
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.user_id)
        .where(PasswordReset.purpose == PURPOSE)
        .where(PasswordReset.used.is_(False))
        .values(used=True)
    )
    db.commit()
    db.refresh(user)
    view = _auth_view(db, user)
    view["message"] = "E-posta doğrulandı. Hoş geldin!"
    return view
