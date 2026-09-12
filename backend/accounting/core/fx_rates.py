"""FX rates (Phase 10B) — one direction, one selection policy, reproducible history.

TRACEABILITY
  rate storage      ← Rahaal `exchange_rates` (JS floats, mutable)        PORT + HARDEN (Decimal128, immutable)
  rate lookup       ← Rahaal "latest rate" helper                         PORT + HARDEN (explicit selection policy)
  destructive update← Rahaal rate edit in place                           LEAVE (refused)

RATE DIRECTION — THE SINGLE CONTRACT (there is exactly one, everywhere):
    rate = how many units of `to_currency` equal ONE unit of `from_currency`
    converted = amount(from) × rate
No function anywhere in the Core uses the inverse direction.

RATE SELECTION POLICY — THE SINGLE POLICY:
    the rate whose `effective_date` is the LATEST value <= the accounting date.
    If no such rate exists → FX_RATE_NOT_FOUND. A newer rate is NEVER used for an older
    date, and "the latest rate available" is never applied silently.
"""
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional

from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from .currency_settings import RATE_SCALE
from .errors import AccountingError
from .journal import utc_now

RATE_INDEX = "uniq_entity_pair_effective"
RATE_LOOKUP_INDEX = "entity_pair_effective_desc"
RATE_DIRECTION = "rate = units of to_currency per 1 unit of from_currency"
RATE_SELECTION_POLICY = "latest effective_date <= accounting date (no silent latest rate)"
MAX_RATE = Decimal("1000000000")


def quantise_rate(value) -> Decimal:
    try:
        raw = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise AccountingError("INVALID_FX_RATE", f"سعر صرف غير صالح: {value!r}")
    if not raw.is_finite():
        raise AccountingError("INVALID_FX_RATE",
                              "سعر صرف غير منتهٍ (NaN/Infinity) غير مقبول")
    if raw <= 0:
        raise AccountingError("INVALID_FX_RATE",
                              f"سعر الصرف يجب أن يكون أكبر من صفر (المُدخل {raw})")
    if raw > MAX_RATE:
        raise AccountingError("FX_RATE_OUT_OF_RANGE",
                              f"سعر الصرف يتجاوز الحد الأقصى ({MAX_RATE})")
    quantised = raw.quantize(Decimal(1).scaleb(-RATE_SCALE), rounding=ROUND_HALF_UP)
    if quantised != raw:
        raise AccountingError(
            "INVALID_FX_RATE_PRECISION",
            f"دقة سعر الصرف تتجاوز {RATE_SCALE} منازل عشرية: {raw} — لا يقوم النظام "
            f"بالتقريب نيابة عنك")
    return quantised


class FXRateStore:
    def __init__(self, database, collection_prefix: str = "accounting_"):
        self._db = database
        self._prefix = collection_prefix

    @property
    def rates(self):
        return self._db[f"{self._prefix}fx_rates"]

    async def ensure_indexes(self) -> List[str]:
        created = []
        # One rate per (entity, pair, effective_date) — a second value for the same instant
        # is a contradiction, not an update.
        await self.rates.create_index(
            [("entity_id", ASCENDING), ("from_currency", ASCENDING),
             ("to_currency", ASCENDING), ("effective_date", ASCENDING)],
            unique=True, name=RATE_INDEX)
        created.append(RATE_INDEX)
        # The ONE selection query: newest effective_date <= date.
        await self.rates.create_index(
            [("entity_id", ASCENDING), ("from_currency", ASCENDING),
             ("to_currency", ASCENDING), ("effective_date", DESCENDING)],
            name=RATE_LOOKUP_INDEX)
        created.append(RATE_LOOKUP_INDEX)
        await self.rates.create_index([("entity_id", ASCENDING), ("id", ASCENDING)],
                                      unique=True, name="uniq_entity_fx_rate_id")
        created.append("uniq_entity_fx_rate_id")
        return created

    async def insert(self, doc: dict) -> bool:
        try:
            await self.rates.insert_one(dict(doc))
            return True
        except DuplicateKeyError:
            return False

    async def get_exact(self, entity_id: str, frm: str, to: str,
                        effective_date) -> Optional[dict]:
        return await self.rates.find_one(
            {"entity_id": entity_id, "from_currency": frm, "to_currency": to,
             "effective_date": effective_date}, {"_id": 0})

    async def get_by_id(self, entity_id: str, rate_id: str) -> Optional[dict]:
        return await self.rates.find_one({"entity_id": entity_id, "id": rate_id},
                                         {"_id": 0})

    async def select_for_date(self, entity_id: str, frm: str, to: str,
                              date) -> Optional[dict]:
        cursor = self.rates.find(
            {"entity_id": entity_id, "from_currency": frm, "to_currency": to,
             "effective_date": {"$lte": date}}, {"_id": 0}) \
            .sort([("effective_date", DESCENDING)]).limit(1)
        rows = await cursor.to_list(length=1)
        return rows[0] if rows else None

    async def list_rates(self, entity_id: str, frm: Optional[str] = None,
                         to: Optional[str] = None, limit: int = 100) -> List[dict]:
        q = {"entity_id": entity_id}
        if frm:
            q["from_currency"] = frm
        if to:
            q["to_currency"] = to
        return await self.rates.find(q, {"_id": 0}) \
            .sort([("effective_date", DESCENDING)]).to_list(length=min(limit, 500))


class FXRateService:
    def __init__(self, rate_store: FXRateStore, currency_service):
        self._store = rate_store
        self._currencies = currency_service

    @staticmethod
    def public(doc: dict) -> dict:
        rate = doc.get("rate")
        return {"id": doc["id"], "from_currency": doc["from_currency"],
                "to_currency": doc["to_currency"],
                "rate": format(rate.to_decimal() if isinstance(rate, Decimal128)
                               else rate, "f"),
                "effective_date": doc["effective_date"].isoformat()
                if hasattr(doc.get("effective_date"), "isoformat")
                else doc.get("effective_date"),
                "source": doc.get("source"),
                "created_at": doc["created_at"].isoformat()
                if hasattr(doc.get("created_at"), "isoformat") else doc.get("created_at"),
                "created_by": doc.get("created_by"),
                "direction": RATE_DIRECTION, "immutable": True}

    async def add_rate(self, entity_id: str, from_currency: str, rate,
                       effective_date, to_currency: Optional[str] = None,
                       source: Optional[str] = None,
                       by: Optional[str] = None) -> dict:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        if not by:
            raise AccountingError("ACTOR_REQUIRED", "هوية المنفّذ مطلوبة")
        if not effective_date:
            raise AccountingError("FX_EFFECTIVE_DATE_REQUIRED",
                                  "تاريخ سريان سعر الصرف مطلوب")
        base = await self._currencies.base_currency(entity_id)
        frm = str(from_currency).strip().upper()
        to = str(to_currency).strip().upper() if to_currency else base
        # Both sides must be configured (active or not: a historical pair stays quotable).
        await self._assert_configured(entity_id, frm)
        await self._assert_configured(entity_id, to)
        if frm == to:
            raise AccountingError(
                "FX_SAME_CURRENCY_RATE",
                f"سعر صرف من {frm} إلى نفسها غير لازم — التحويل داخل العملة نفسها "
                f"بمعامل 1 ولا يُخزَّن")
        value = quantise_rate(rate)
        if effective_date.tzinfo is None:
            from datetime import timezone
            effective_date = effective_date.replace(tzinfo=timezone.utc)

        existing = await self._store.get_exact(entity_id, frm, to, effective_date)
        if existing:
            current = existing["rate"].to_decimal() \
                if isinstance(existing["rate"], Decimal128) else existing["rate"]
            if current == value:
                return {"created": False, "idempotent_replay": True,
                        "rate": self.public(existing)}
            # A rate that history may already have been computed with is never rewritten.
            raise AccountingError(
                "FX_RATE_IMMUTABLE",
                f"يوجد سعر {current} لنفس التاريخ ({effective_date.date()}) للزوج "
                f"{frm}/{to} — لا يُعدَّل سعر قد استُخدم محاسبياً؛ أضف سعراً بتاريخ "
                f"سريان جديد", 409, existing_rate=format(current, "f"))

        doc = {"id": str(uuid.uuid4()), "entity_id": entity_id,
               "from_currency": frm, "to_currency": to,
               "rate": Decimal128(value), "effective_date": effective_date,
               "source": (source or "manual").strip(), "created_at": utc_now(),
               "created_by": by, "direction": RATE_DIRECTION}
        if not await self._store.insert(doc):
            existing = await self._store.get_exact(entity_id, frm, to, effective_date)
            return {"created": False, "idempotent_replay": True,
                    "rate": self.public(existing)}
        return {"created": True, "rate": self.public(doc),
                "direction": RATE_DIRECTION,
                "selection_policy": RATE_SELECTION_POLICY}

    async def resolve(self, entity_id: str, from_currency: str, to_currency: str,
                      date) -> dict:
        """The ONE rate-selection implementation used by every FX path."""
        doc = await self._store.select_for_date(entity_id, from_currency, to_currency,
                                                 date)
        if not doc:
            raise AccountingError(
                "FX_RATE_NOT_FOUND",
                f"لا يوجد سعر صرف {from_currency}/{to_currency} ساري بتاريخ "
                f"{date.date()} أو قبله — لن يُستخدم سعر أحدث بصمت", 409,
                selection_policy=RATE_SELECTION_POLICY)
        return doc

    async def list_rates(self, entity_id: str, from_currency: Optional[str] = None,
                         to_currency: Optional[str] = None,
                         limit: int = 100) -> dict:
        docs = await self._store.list_rates(
            entity_id, str(from_currency).strip().upper() if from_currency else None,
            str(to_currency).strip().upper() if to_currency else None, limit)
        return {"entity_id": entity_id, "direction": RATE_DIRECTION,
                "selection_policy": RATE_SELECTION_POLICY, "rate_scale": RATE_SCALE,
                "items": [self.public(d) for d in docs]}

    async def _assert_configured(self, entity_id: str, code: str) -> None:
        config = await self._currencies.require(entity_id)
        if code not in [c["code"] for c in config.get("currencies") or []]:
            raise AccountingError("CURRENCY_NOT_CONFIGURED",
                                  f"العملة {code} غير مكوّنة لهذه الجهة", 409)
