"""Şifre sıfırlama — e-posta kodu + admin sıfırlama."""

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
    find_user_by_login,
    hash_password,
    normalize_email,
    normalize_phone,
)

logger = logging.getLogger(__name__)
CODE_TTL_MINUTES = 20
CODE_LENGTH = 6


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str, user_id: str) -> str:
    raw = f"{code}:{user_id}:{settings.jwt_secret}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _make_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def _send_reset_email(to_email: str, code: str, display_name: str) -> bool:
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        return False
    from_addr = (settings.resend_from_email or "").strip() or "Tilko <onboarding@resend.dev>"
    name = (display_name or "").strip() or "Tilko kullanıcısı"
    subject = "Tilko şifre sıfırlama kodu"
    text = (
        f"Merhaba {name},\n\n"
        f"Şifre sıfırlama kodun: {code}\n"
        f"Kod {CODE_TTL_MINUTES} dakika geçerli.\n\n"
        f"Bu isteği sen yapmadıysan yok say.\n"
        f"— Tilko\n"
        f"{settings.public_app_url}/giris\n"
    )
    html = (
        f"<p>Merhaba <strong>{name}</strong>,</p>"
        f"<p>Şifre sıfırlama kodun:</p>"
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
            logger.warning("Resend hata %s: %s", response.status_code, response.text[:300])
            return False
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Resend e-posta gönderilemedi")
        return False


def request_password_reset(db: Session, *, email: str = "", phone: str = "") -> dict:
    """Kod üretir. Hesap yoksa da aynı genel mesaj (sızıntı yok)."""
    mail = normalize_email(email) if (email or "").strip() else ""
    tel = ""
    if (phone or "").strip():
        try:
            tel = normalize_phone(phone)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if not mail and not tel:
        raise ValueError("E-posta veya telefon gerekli.")

    identifier = mail or tel
    user = find_user_by_login(db, identifier)
    generic = {
        "ok": True,
        "sent": False,
        "channel": "email" if mail else "phone",
        "destination_hint": "",
        "message": (
            "Kayıtlı bir hesap varsa sıfırlama kodu gönderildi. "
            "Birkaç dakika içinde gelmezse spam klasörüne bak."
        ),
        "debug_code": "",
    }

    if user is None:
        return generic
    if not (user.password_hash or "").strip() and (user.google_sub or "").strip():
        return {
            **generic,
            "message": (
                "Bu hesap Google ile açılmış. Şifre yerine Google ile giriş yap."
            ),
        }

    code = _make_code()
    channel = "email" if mail else "phone"
    dest = mail or tel
    # Eski kodları iptal
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.user_id)
        .where(PasswordReset.used.is_(False))
        .values(used=True)
    )
    row = PasswordReset(
        user_id=user.user_id,
        code_hash=_hash_code(code, user.user_id),
        channel=channel,
        destination=dest,
        expires_at=_utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
        used=False,
    )
    db.add(row)
    db.commit()

    sent = False
    hint = ""
    if channel == "email" and mail:
        sent = _send_reset_email(mail, code, user.display_name or "")
        parts = mail.split("@")
        hint = f"{parts[0][:2]}***@{parts[1]}" if len(parts) == 2 else "***"
    else:
        # SMS yok: telefonda kayıtlıysa e-postaya yönlendir veya admin
        hint = f"***{tel[-4:]}" if tel else ""
        if (user.email or "").strip():
            sent = _send_reset_email(user.email, code, user.display_name or "")
            channel = "email"
            mail_parts = user.email.split("@")
            hint = (
                f"{mail_parts[0][:2]}***@{mail_parts[1]}"
                if len(mail_parts) == 2
                else "***"
            )

    out = {
        **generic,
        "sent": sent,
        "channel": channel,
        "destination_hint": hint,
    }
    if sent:
        out["message"] = (
            f"Sıfırlama kodu {hint or 'kayıtlı adrese'} gönderildi. "
            f"{CODE_TTL_MINUTES} dakika geçerli."
        )
    elif not (settings.resend_api_key or "").strip():
        out["message"] = (
            "Şifre sıfırlama e-postası henüz yapılandırılmamış. "
            "Google ile giriş dene veya destek / admin ile yeni şifre iste."
        )
        if not settings.is_production:
            out["debug_code"] = code
            out["message"] += f" (geliştirme kodu: {code})"
    else:
        out["message"] = (
            "Kod oluşturuldu ama e-posta gönderilemedi. Biraz sonra tekrar dene "
            "veya Google ile giriş yap."
        )
        if not settings.is_production:
            out["debug_code"] = code
    return out


def reset_password_with_code(
    db: Session,
    *,
    email: str = "",
    phone: str = "",
    code: str = "",
    new_password: str = "",
) -> dict:
    mail = normalize_email(email) if (email or "").strip() else ""
    tel = normalize_phone(phone) if (phone or "").strip() else ""
    identifier = mail or tel
    if not identifier:
        raise ValueError("E-posta veya telefon gerekli.")
    pin = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(pin) != CODE_LENGTH:
        raise ValueError(f"{CODE_LENGTH} haneli kodu gir.")
    if len(new_password or "") < 8:
        raise ValueError("Yeni şifre en az 8 karakter olmalı.")

    user = find_user_by_login(db, identifier)
    if user is None:
        raise ValueError("Kod geçersiz veya süresi dolmuş.")

    now = _utcnow()
    rows = list(
        db.scalars(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.user_id)
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

    user.password_hash = hash_password(new_password)
    match.used = True
    db.add(user)
    db.add(match)
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.user_id)
        .where(PasswordReset.used.is_(False))
        .values(used=True)
    )
    db.commit()
    return {
        "ok": True,
        "user_id": user.user_id,
        "message": "Şifren güncellendi. Yeni şifrenle giriş yapabilirsin.",
    }


def admin_set_password(db: Session, user_id: str, new_password: str) -> dict:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id gerekli.")
    if len(new_password or "") < 8:
        raise ValueError("Şifre en az 8 karakter olmalı.")
    user = db.get(User, uid)
    if user is None:
        raise ValueError("Kullanıcı bulunamadı.")
    user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    return {
        "ok": True,
        "user_id": uid,
        "message": "Şifre admin tarafından güncellendi.",
    }
