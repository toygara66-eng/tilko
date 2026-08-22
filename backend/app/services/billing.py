"""Google Play abonelik doğrulama — sandbox + production token."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import PlayPurchase, User
from app.services.penalty import get_or_create_user

logger = logging.getLogger(__name__)

SANDBOX_PREFIX = "gp_sandbox."
PRODUCTS = {
    "tilko_pro_monthly": {
        "id": "tilko_pro_monthly",
        "label": "Aylık Tilko Pro",
        "period": "monthly",
        "days": 31,
        "price_try": 149,
        "price_label": "149 TL / ay",
    },
    "tilko_pro_yearly": {
        "id": "tilko_pro_yearly",
        "label": "Yıllık Tilko Pro",
        "period": "yearly",
        "days": 366,
        "price_try": 990,
        "price_label": "990 TL / yıl",
    },
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def catalog() -> dict:
    return {
        "package_name": settings.play_package_name,
        "sandbox": bool(settings.play_billing_sandbox),
        "plans": list(PRODUCTS.values()),
    }


def refresh_entitlement(db: Session, user: User) -> User:
    """Süresi biten aboneliği düşür — kota kontrolünden önce çağır."""
    expires = _aware(getattr(user, "subscription_expires_at", None))
    status = (getattr(user, "subscription_status", "") or "").strip().lower()
    if user.is_premium and expires and expires <= utcnow():
        user.is_premium = False
        user.subscription_status = "expired"
        db.add(user)
    elif user.is_premium and status in {"revoked", "expired"}:
        user.is_premium = False
        db.add(user)
    return user


def public_status(user: User) -> dict:
    expires = _aware(getattr(user, "subscription_expires_at", None))
    return {
        "is_premium": bool(user.is_premium),
        "subscription_status": getattr(user, "subscription_status", "") or "none",
        "product_id": getattr(user, "subscription_product_id", "") or "",
        "expires_at": expires.isoformat() if expires else None,
        "sandbox": bool(settings.play_billing_sandbox),
        "package_name": settings.play_package_name,
        "plans": list(PRODUCTS.values()),
    }


def grant_pro_subscription(db: Session, user: User, days: int = 31) -> User:
    """Sazan Avı birincilerine bir ay Pro — Play token olmadan prize statüsü."""
    _grant(user, "tilko_pro_monthly", days, status="prize")
    db.add(user)
    return user


def _grant(user: User, product_id: str, days: int, status: str = "active") -> None:
    now = utcnow()
    current = _aware(getattr(user, "subscription_expires_at", None))
    start = current if current and current > now and user.is_premium else now
    user.is_premium = True
    user.subscription_product_id = product_id
    user.subscription_status = status
    user.subscription_expires_at = start + timedelta(days=days)


def _revoke(user: User, status: str = "expired") -> None:
    user.is_premium = False
    user.subscription_status = status


def _product_or_raise(product_id: str) -> dict:
    item = PRODUCTS.get((product_id or "").strip())
    if item is None:
        raise ValueError("Bilinmeyen ürün. tilko_pro_monthly veya tilko_pro_yearly.")
    return item


def _sandbox_payload(user_id: str, product_id: str, token: str) -> dict:
    if not settings.play_billing_sandbox:
        raise PermissionError("Sandbox satın alma kapalı. Google Play token gerekli.")
    if not token.startswith(SANDBOX_PREFIX):
        raise ValueError("Test token gp_sandbox. ile başlamalı.")
    parts = token.split(".")
    # gp_sandbox.{user_id}.{product_id}.{nonce}
    if len(parts) < 4:
        raise ValueError("Geçersiz test token.")
    claimed_user = parts[1]
    claimed_product = parts[2]
    if claimed_user != user_id:
        raise PermissionError("Token bu hesaba ait değil.")
    if claimed_product != product_id:
        raise ValueError("Ürün ile token uyuşmuyor.")
    product = _product_or_raise(product_id)
    return {
        "acknowledged": True,
        "expiryTimeMillis": str(int((utcnow() + timedelta(days=product["days"])).timestamp() * 1000)),
        "sandbox": True,
        "product_id": product_id,
    }


def _google_access_token() -> str:
    raw_path = (settings.play_service_account_file or "").strip()
    if not raw_path:
        raise RuntimeError("PLAY_SERVICE_ACCOUNT_FILE yok.")
    path = Path(raw_path)
    if not path.is_file():
        raise RuntimeError("Play servis hesabı dosyası bulunamadı.")
    info = json.loads(path.read_text(encoding="utf-8"))
    now = int(time.time())
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode()
    claim = {
        "iss": info["client_email"],
        "scope": "https://www.googleapis.com/auth/androidpublisher",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    body = base64.urlsafe_b64encode(json.dumps(claim, separators=(",", ":")).encode()).rstrip(b"=").decode()
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Play doğrulama için cryptography paketi gerekli.") from exc
    key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
    sig = key.sign(f"{header}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{body}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        response.raise_for_status()
        return str(response.json().get("access_token") or "")


def verify_google_token(product_id: str, purchase_token: str) -> dict:
    package = settings.play_package_name
    access = _google_access_token()
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
        f"{package}/purchases/subscriptions/{product_id}/tokens/{purchase_token}"
    )
    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, headers={"Authorization": f"Bearer {access}"})
        if response.status_code == 404:
            raise ValueError("Google Play bu satın almayı tanımıyor.")
        response.raise_for_status()
        data = response.json()
    expiry_ms = int(data.get("expiryTimeMillis") or 0)
    if expiry_ms and expiry_ms < int(utcnow().timestamp() * 1000):
        raise ValueError("Abonelik süresi dolmuş.")
    # paymentState 0=pending 1=received 2=free trial 3=pending deferred
    state = data.get("paymentState")
    if state not in (1, 2, None):
        raise ValueError("Ödeme henüz onaylanmadı.")
    return data


def acknowledge_google_purchase(product_id: str, purchase_token: str) -> None:
    """Play aboneliğini onayla; onaylanmazsa Google otomatik iade edebilir."""
    package = settings.play_package_name
    access = _google_access_token()
    url = (
        "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
        f"{package}/purchases/subscriptions/{product_id}/tokens/{purchase_token}:acknowledge"
    )
    with httpx.Client(timeout=20.0) as client:
        response = client.post(url, headers={"Authorization": f"Bearer {access}"}, json={})
        if response.status_code in {200, 204}:
            return
        if response.status_code == 400 and "already" in (response.text or "").lower():
            return
        logger.warning("Play acknowledge başarısız %s: %s", response.status_code, response.text[:200])


def _apply_receipt(
    db: Session,
    user: User,
    product_id: str,
    purchase_token: str,
    order_id: str,
    platform: str,
    receipt: dict,
    *,
    activate: bool,
) -> PlayPurchase:
    product = _product_or_raise(product_id)
    digest = token_hash(purchase_token)
    row = db.scalars(
        select(PlayPurchase).where(PlayPurchase.purchase_token_hash == digest)
    ).first()
    expiry_ms = int(receipt.get("expiryTimeMillis") or 0)
    if expiry_ms:
        expires = datetime.fromtimestamp(expiry_ms / 1000, tz=timezone.utc)
    else:
        expires = utcnow() + timedelta(days=product["days"])
    if row is None:
        row = PlayPurchase(
            user_id=user.user_id,
            product_id=product_id,
            purchase_token_hash=digest,
            order_id=order_id or "",
            platform=platform,
            status="active" if activate else "canceled",
            expires_at=expires,
            raw_json=json.dumps(receipt, ensure_ascii=False)[:8000],
        )
        db.add(row)
    else:
        if row.user_id != user.user_id:
            raise PermissionError("Bu token başka bir hesaba kayıtlı.")
        row.product_id = product_id
        row.order_id = order_id or row.order_id
        row.status = "active" if activate else row.status
        row.expires_at = expires
        row.raw_json = json.dumps(receipt, ensure_ascii=False)[:8000]
        row.updated_at = utcnow()
    user.play_purchase_token_hash = digest
    if activate:
        days = max(1, int((expires - utcnow()).total_seconds() // 86400) or product["days"])
        _grant(user, product_id, days)
        user.subscription_expires_at = expires
    db.add(user)
    db.commit()
    db.refresh(user)
    db.refresh(row)
    return row


def verify_purchase(
    db: Session,
    *,
    user_id: str,
    product_id: str,
    purchase_token: str,
    order_id: str = "",
    platform: str = "",
) -> dict:
    user = get_or_create_user(db, user_id)
    token = (purchase_token or "").strip()
    sku = (product_id or "").strip()
    if not token or not sku:
        raise ValueError("purchase_token ve product_id gerekli.")
    _product_or_raise(sku)
    if token.startswith(SANDBOX_PREFIX):
        receipt = _sandbox_payload(user_id, sku, token)
        plat = "sandbox"
    else:
        if settings.play_billing_sandbox and not (settings.play_service_account_file or "").strip():
            raise ValueError(
                "Canlı Play token için PLAY_SERVICE_ACCOUNT_FILE ve "
                "PLAY_BILLING_SANDBOX=false gerekir."
            )
        receipt = verify_google_token(sku, token)
        plat = platform or "android"
        try:
            if not receipt.get("acknowledgementState"):
                acknowledge_google_purchase(sku, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Play acknowledge atlandı: %s", exc)
    _apply_receipt(
        db,
        user,
        sku,
        token,
        order_id,
        plat,
        receipt,
        activate=True,
    )
    return {
        "ok": True,
        "is_premium": True,
        "message": "Tilko Pro açıldı. Kota kalktı.",
        **public_status(user),
    }


def handle_rtdn(db: Session, body: dict) -> dict:
    """Google Play Real-time Developer Notification."""
    payload = body or {}
    if "message" in payload and isinstance(payload["message"], dict):
        raw = payload["message"].get("data") or ""
        try:
            decoded = base64.b64decode(raw + "==").decode("utf-8")
            payload = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("RTDN gövdesi okunamadı.") from exc
    note = payload.get("subscriptionNotification") or {}
    token = str(note.get("purchaseToken") or payload.get("purchase_token") or "").strip()
    product_id = str(
        note.get("subscriptionId") or payload.get("product_id") or ""
    ).strip()
    ntype = int(note.get("notificationType") or payload.get("notification_type") or 0)
    if not token:
        raise ValueError("purchaseToken yok.")
    digest = token_hash(token)
    row = db.scalars(
        select(PlayPurchase).where(PlayPurchase.purchase_token_hash == digest)
    ).first()
    user = db.get(User, row.user_id) if row else None
    if user is None:
        # Token henüz verify edilmemişse Google'dan çekip bekletmeyiz;
        # kullanıcı uygulamayı açınca /subscription/verify bağlar.
        logger.info("RTDN: kayıtlı token yok (%s)", ntype)
        return {"ok": True, "linked": False, "notification_type": ntype}

    revoke_types = {12, 13}  # revoked, expired
    cancel_types = {3}  # canceled — süre bitene kadar Pro kalsın
    renew_types = {1, 2, 4, 7}  # recovered, renewed, purchased, restarted

    if ntype in revoke_types:
        _revoke(user, "revoked" if ntype == 12 else "expired")
        if row:
            row.status = user.subscription_status
        db.commit()
        return {"ok": True, "is_premium": False, "notification_type": ntype}

    if ntype in cancel_types:
        user.subscription_status = "canceled"
        if row:
            row.status = "canceled"
        db.commit()
        return {"ok": True, "is_premium": bool(user.is_premium), "notification_type": ntype}

    if ntype in renew_types and product_id:
        try:
            receipt = verify_google_token(product_id, token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RTDN Google doğrulama başarısız: %s", exc)
            return {"ok": False, "error": "google_verify_failed", "notification_type": ntype}
        _apply_receipt(
            db,
            user,
            product_id,
            token,
            "",
            "rtdn",
            receipt,
            activate=True,
        )
        return {"ok": True, "is_premium": True, "notification_type": ntype}

    return {"ok": True, "notification_type": ntype, "ignored": True}
