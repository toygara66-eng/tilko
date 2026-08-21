"""Tek / çok kullanımlık indirim kuponu — doğrulama, limit ve toplu üretim."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import PromoCode, PromoRedemption
from app.services.billing import PRODUCTS, utcnow
from app.services.penalty import get_or_create_user

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_]{2,31}$")
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_FULL = "full"


def normalize_code(raw: str) -> str:
    return (raw or "").strip().upper().replace(" ", "")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parse_expiry(raw: str | None) -> datetime | None:
    stamp = (raw or "").strip()
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Son kullanma tarihi ISO formatında olmalı (örn. 2026-12-31T23:59:00).") from exc
    return _aware(parsed)


def _loads_users(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in data:
        uid = str(item or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def _quote(original: float, discount_type: str, value: float) -> tuple[float, float]:
    price = max(0.0, float(original))
    kind = (discount_type or "").strip().lower()
    amount = float(value)
    if kind == "percentage":
        cut = round(price * (amount / 100.0), 2)
    elif kind == "fixed":
        cut = round(amount, 2)
    else:
        raise ValueError("discount_type percentage veya fixed olmalı.")
    cut = min(max(cut, 0.0), price)
    payable = round(max(0.0, price - cut), 2)
    return cut, payable


def _compute_status(row: PromoCode, now: datetime | None = None) -> str:
    moment = now or utcnow()
    expires = _aware(row.expires_at)
    if expires and expires <= moment:
        return STATUS_EXPIRED
    max_uses = int(row.max_uses or 0)
    if max_uses > 0 and int(row.used_count or 0) >= max_uses:
        return STATUS_FULL
    return STATUS_ACTIVE


def _status(row: PromoCode, now: datetime | None = None) -> str:
    return _compute_status(row, now)


def _sync_status(row: PromoCode, now: datetime | None = None) -> str:
    state = _compute_status(row, now)
    if (getattr(row, "status", "") or "") != state:
        row.status = state
    return state


def _public_code(row: PromoCode, redemptions: list[PromoRedemption] | None = None) -> dict:
    expires = _aware(row.expires_at)
    max_uses = int(row.max_uses or 0)
    used = int(row.used_count or 0)
    remaining = None if max_uses == 0 else max(0, max_uses - used)
    people = [item.user_id for item in (redemptions or [])]
    if not people:
        people = _loads_users(getattr(row, "used_by_json", "") or "[]")
    teacher_id = (getattr(row, "created_by_teacher_id", "") or "").strip()
    return {
        "id": row.id,
        "code": row.code,
        "discount_type": row.discount_type,
        "value": float(row.value),
        "max_uses": max_uses,
        "used_count": used,
        "remaining": remaining,
        "used_by": people,
        "created_by_teacher_id": teacher_id,
        "enroll_to_class": bool(getattr(row, "enroll_to_class", False)),
        "expires_at": expires.isoformat() if expires else None,
        "created_at": _aware(row.created_at).isoformat() if row.created_at else None,
        "status": _status(row),
        "redemptions": [
            {
                "user_id": item.user_id,
                "product_id": item.product_id,
                "original_price": float(item.original_price),
                "discount_amount": float(item.discount_amount),
                "payable_amount": float(item.payable_amount),
                "used_at": _aware(item.created_at).isoformat() if item.created_at else None,
            }
            for item in (redemptions or [])
        ],
    }


def _validate_spec(code: str, discount_type: str, value: float, max_uses: int) -> tuple[str, str, float, int]:
    label = normalize_code(code)
    if not CODE_RE.match(label):
        raise ValueError("Kod 3-32 karakter, harf/rakam (tire serbest). Örn: TILKO20")
    kind = (discount_type or "").strip().lower()
    if kind not in {"percentage", "fixed"}:
        raise ValueError("discount_type percentage veya fixed olmalı.")
    amount = float(value)
    if kind == "percentage" and not (0 < amount <= 100):
        raise ValueError("Yüzde indirim 0 ile 100 arasında olmalı.")
    if kind == "fixed" and amount <= 0:
        raise ValueError("Sabit indirim 0'dan büyük olmalı.")
    uses = max(0, int(max_uses or 0))
    return label, kind, amount, uses


def _bulk_labels(base: str, quantity: int) -> list[str]:
    count = max(1, min(int(quantity or 1), 500))
    if count == 1:
        return [base]
    width = max(3, len(str(count)))
    stem = base[: max(1, 31 - (width + 1))]
    labels = []
    for index in range(1, count + 1):
        candidate = f"{stem}-{index:0{width}d}"
        if not CODE_RE.match(candidate):
            raise ValueError("Toplu kod üretilemedi. Daha kısa bir kök kod yaz.")
        labels.append(candidate)
    return labels


def create_promo(
    db: Session,
    *,
    code: str,
    discount_type: str,
    value: float,
    max_uses: int = 0,
    expires_at: str | None = None,
    quantity: int = 1,
    created_by_teacher_id: str = "",
    enroll_to_class: bool = False,
) -> dict:
    label, kind, amount, uses = _validate_spec(code, discount_type, value, max_uses)
    expiry = _parse_expiry(expires_at)
    labels = _bulk_labels(label, quantity)
    teacher_id = (created_by_teacher_id or "").strip()
    enroll = bool(enroll_to_class) and bool(teacher_id)
    existing = {
        row.code
        for row in db.scalars(select(PromoCode).where(PromoCode.code.in_(labels))).all()
    }
    clash = [item for item in labels if item in existing]
    if clash:
        raise ValueError(f"Bu kupon kodu zaten var: {', '.join(clash[:5])}")
    created: list[PromoCode] = []
    for item in labels:
        row = PromoCode(
            code=item,
            discount_type=kind,
            value=amount,
            max_uses=uses,
            used_count=0,
            used_by_json="[]",
            status=STATUS_ACTIVE,
            created_by_teacher_id=teacher_id,
            enroll_to_class=enroll,
            expires_at=expiry,
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    coupons = [_public_code(row, []) for row in created]
    if len(coupons) == 1:
        message = f"{coupons[0]['code']} oluşturuldu."
    else:
        message = f"{len(coupons)} kupon üretildi ({coupons[0]['code']} … {coupons[-1]['code']})."
    return {"ok": True, "count": len(coupons), "coupons": coupons, "message": message}


def list_promos(db: Session, teacher_id: str | None = None) -> dict:
    query = select(PromoCode).order_by(PromoCode.created_at.desc())
    owned = (teacher_id or "").strip()
    if owned:
        query = query.where(PromoCode.created_by_teacher_id == owned)
    rows = list(db.scalars(query).all())
    redemptions = list(
        db.scalars(select(PromoRedemption).order_by(PromoRedemption.created_at.desc())).all()
    )
    by_promo: dict[int, list[PromoRedemption]] = {}
    for item in redemptions:
        by_promo.setdefault(int(item.promo_id), []).append(item)
    dirty = False
    now = utcnow()
    for row in rows:
        before = getattr(row, "status", "") or ""
        if _sync_status(row, now) != before:
            dirty = True
    if dirty:
        db.commit()
    coupons = [_public_code(row, by_promo.get(row.id, [])) for row in rows]
    return {"coupons": coupons, "count": len(coupons)}


def _quote_payload(
    row: PromoCode,
    sku: str,
    original: float,
    discount: float,
    payable: float,
    extra: dict | None = None,
) -> dict:
    lira = int(discount) if discount == int(discount) else discount
    pay = int(payable) if payable == int(payable) else payable
    message = f"{lira} TL indirim uygulandı, ödenecek tutar: {pay} TL"
    payload = {
        "ok": True,
        "code": row.code,
        "discount_type": row.discount_type,
        "value": float(row.value),
        "product_id": sku,
        "original_price": original,
        "discount_amount": discount,
        "payable_amount": payable,
        "message": message,
        "status": _status(row),
        "used_count": int(row.used_count or 0),
        "max_uses": int(row.max_uses or 0),
        "classroom_joined": False,
        "teacher_id": "",
        "teacher_name": "",
        "join_message": "",
    }
    if extra:
        payload.update(extra)
        if extra.get("join_message") and extra.get("classroom_joined"):
            payload["message"] = f"{message} {extra['join_message']}"
    return payload


def _classroom_join(db: Session, user_id: str, row: PromoCode) -> dict:
    teacher_id = (getattr(row, "created_by_teacher_id", "") or "").strip()
    enroll = bool(getattr(row, "enroll_to_class", False))
    if not teacher_id or not enroll:
        return {}
    from app.services import teacher as teacher_service

    linked = teacher_service.enroll_student(
        db,
        teacher_id,
        user_id,
        source="promo",
        promo_code=row.code,
    )
    if not linked:
        return {}
    name = teacher_service.display_name_of(db, teacher_id)
    return {
        "classroom_joined": True,
        "teacher_id": teacher_id,
        "teacher_name": name,
        "join_message": (
            f"Tebrikler! {name} hocamın sınıfına başarıyla katıldın. "
            "Artık analizlerin hocanla paylaşılıyor!"
        ),
    }


def apply_promo(db: Session, user_id: str, code: str, product_id: str = "") -> dict:
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("Kullanıcı kimliği gerekli.")
    get_or_create_user(db, uid)
    label = normalize_code(code)
    if not label:
        raise ValueError("İndirim kodu gir.")
    sku = (product_id or "").strip() or "tilko_pro_monthly"
    product = PRODUCTS.get(sku)
    if product is None:
        raise ValueError("Bilinmeyen ürün. Aylık veya yıllık plan seç.")

    row = db.scalar(select(PromoCode).where(PromoCode.code == label))
    if row is None:
        raise ValueError("Bu kupon geçersiz.")

    now = utcnow()
    expires = _aware(row.expires_at)
    if expires and expires <= now:
        row.status = STATUS_EXPIRED
        db.add(row)
        db.commit()
        raise ValueError("Bu kuponun süresi doldu.")

    existing = db.scalar(
        select(PromoRedemption).where(
            PromoRedemption.promo_id == row.id,
            PromoRedemption.user_id == uid,
        )
    )
    original = float(product["price_try"])
    discount, payable = _quote(original, row.discount_type, float(row.value))
    if existing is not None:
        existing.product_id = sku
        existing.original_price = original
        existing.discount_amount = discount
        existing.payable_amount = payable
        db.add(existing)
        extra = _classroom_join(db, uid, row)
        db.commit()
        db.refresh(row)
        return _quote_payload(row, sku, original, discount, payable, extra)

    max_uses = int(row.max_uses or 0)
    if max_uses > 0 and int(row.used_count or 0) >= max_uses:
        row.status = STATUS_FULL
        db.add(row)
        db.commit()
        raise ValueError("Bu kuponun kullanım limiti doldu.")

    result = db.execute(
        update(PromoCode)
        .where(PromoCode.id == row.id)
        .where(or_(PromoCode.max_uses == 0, PromoCode.used_count < PromoCode.max_uses))
        .values(used_count=PromoCode.used_count + 1)
    )
    if result.rowcount != 1:
        db.expire(row)
        db.refresh(row)
        _sync_status(row, now)
        db.add(row)
        db.commit()
        raise ValueError("Bu kuponun kullanım limiti doldu.")

    db.flush()
    db.expire(row)
    db.refresh(row)
    people = _loads_users(getattr(row, "used_by_json", "") or "[]")
    if uid not in people:
        people.append(uid)
    row.used_by_json = json.dumps(people, ensure_ascii=False)
    row.status = STATUS_FULL if max_uses > 0 and int(row.used_count or 0) >= max_uses else STATUS_ACTIVE
    db.add(row)
    db.add(
        PromoRedemption(
            promo_id=row.id,
            code=row.code,
            user_id=uid,
            product_id=sku,
            original_price=original,
            discount_amount=discount,
            payable_amount=payable,
        )
    )
    extra = _classroom_join(db, uid, row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fresh = db.scalar(select(PromoCode).where(PromoCode.id == row.id))
        if fresh is None:
            raise ValueError("Bu kupon geçersiz.")
        extra = _classroom_join(db, uid, fresh)
        db.commit()
        return _quote_payload(fresh, sku, original, discount, payable, extra)
    db.refresh(row)
    return _quote_payload(row, sku, original, discount, payable, extra)
