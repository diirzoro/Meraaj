"""Entity currency configuration (Phase 10A) — the Core still knows NO project currency.

TRACEABILITY
  currency configuration ← Rahaal `CURRENCIES = ['USD','SAR','YER']` in source       ADAPT (per-entity data)
  base currency          ← Rahaal `BASE_CURRENCY = 'YER'` hardcoded                  HARDEN (explicit, per entity)
  currency deactivation  ← (no Rahaal equivalent)                                     NEW
  base currency change   ← Rahaal free reassignment                                   HARDEN (blocked once history exists)

OPEN-002 (Base Currency) IS CLOSED HERE: an entity must declare its base currency
EXPLICITLY before any FX operation. It is never inferred from the first journal and never
defaults to a specific code.
"""
import uuid
from typing import List, Optional

from pymongo import ASCENDING

from .errors import AccountingError
from .journal import utc_now
from .money import DEFAULT_SCALE

CURRENCY_SETTINGS_INDEX = "uniq_entity_currency_settings"
#: FX rates need more precision than money; monetary amounts keep the Phase 3 policy.
RATE_SCALE = 8


class CurrencySettingsStore:
    def __init__(self, database, collection_prefix: str = "accounting_"):
        self._db = database
        self._prefix = collection_prefix

    @property
    def settings(self):
        return self._db[f"{self._prefix}currency_settings"]

    async def ensure_indexes(self) -> List[str]:
        await self.settings.create_index([("entity_id", ASCENDING)], unique=True,
                                         name=CURRENCY_SETTINGS_INDEX)
        return [CURRENCY_SETTINGS_INDEX]

    async def get(self, entity_id: str) -> Optional[dict]:
        return await self.settings.find_one({"entity_id": entity_id}, {"_id": 0})

    async def upsert(self, entity_id: str, fields: dict) -> None:
        await self.settings.update_one(
            {"entity_id": entity_id},
            {"$set": fields,
             "$setOnInsert": {"id": str(uuid.uuid4()), "entity_id": entity_id,
                              "created_at": utc_now()}},
            upsert=True)


class EntityCurrencyService:
    """Generic policy holder. No business-specific currency logic lives here: the Core only
    enforces *configured*, *allowed* and *active*."""

    def __init__(self, settings_store: CurrencySettingsStore, journal_store):
        self._store = settings_store
        self._journal = journal_store

    # ----------------------------------------------------------------- configure
    async def configure(self, entity_id: str, base_currency: str,
                        currencies: List[str], by: Optional[str] = None,
                        precision: int = DEFAULT_SCALE) -> dict:
        entity_id = self._entity(entity_id)
        base = self._code(base_currency)
        codes = [self._code(c) for c in (currencies or [])]
        codes = list(dict.fromkeys(codes + [base]))
        if int(precision) != DEFAULT_SCALE:
            # The monetary policy of Phase 3 is not changed silently by a currency setting.
            raise AccountingError(
                "CURRENCY_PRECISION_UNSUPPORTED",
                f"دقة المبالغ ثابتة على {DEFAULT_SCALE} منزلتين بحسب سياسة النقد "
                f"(المرحلة 3) — تغييرها يحتاج قراراً معماريًا مستقلاً")

        existing = await self._store.get(entity_id)
        if existing and existing.get("base_currency") \
                and existing["base_currency"] != base:
            if await self._journal.count_any(entity_id):
                raise AccountingError(
                    "BASE_CURRENCY_CHANGE_REQUIRES_MIGRATION",
                    f"العملة الأساس الحالية {existing['base_currency']} ويوجد تاريخ "
                    f"محاسبي مُرحَّل — تغييرها إلى {base} يتطلب عملية ترحيل/إعادة تقييم "
                    f"مُحكمة ولا يُنفَّذ كتحديث عادي", 409,
                    current_base=existing["base_currency"], requested_base=base)
        if existing:
            # A currency that already carries history can never be dropped from the
            # configuration as if it had never existed.
            used = await self._journal.entity_currencies(entity_id)
            missing = [c for c in used if c not in codes]
            if missing:
                raise AccountingError(
                    "CURRENCY_HAS_HISTORY",
                    f"العملات {', '.join(missing)} لها حركات مُرحَّلة — لا يمكن إزالتها "
                    f"من التكوين (يمكن تعطيلها فقط)", 409, currencies=missing)

        active = {c: True for c in codes}
        for row in (existing or {}).get("currencies") or []:
            if row["code"] in active:
                active[row["code"]] = bool(row.get("active", True))
        active[base] = True
        await self._store.upsert(entity_id, {
            "base_currency": base,
            "currencies": [{"code": c, "active": active[c],
                            "precision": DEFAULT_SCALE} for c in codes],
            "rate_scale": RATE_SCALE,
            "updated_at": utc_now(), "updated_by": by,
        })
        return await self.describe(entity_id)

    async def set_active(self, entity_id: str, currency: str, active: bool,
                         by: Optional[str] = None) -> dict:
        entity_id = self._entity(entity_id)
        code = self._code(currency)
        config = await self.require(entity_id)
        if code not in [c["code"] for c in config["currencies"]]:
            raise AccountingError("CURRENCY_NOT_CONFIGURED",
                                  f"العملة {code} غير مكوّنة لهذه الجهة", 404)
        if not active and code == config["base_currency"]:
            raise AccountingError(
                "BASE_CURRENCY_CANNOT_BE_DEACTIVATED",
                f"{code} هي العملة الأساس — تعطيلها يحتاج تغييراً مُحكمًا للعملة الأساس",
                409)
        rows = [{**c, "active": bool(active)} if c["code"] == code else c
                for c in config["currencies"]]
        await self._store.upsert(entity_id, {"currencies": rows,
                                             "updated_at": utc_now(),
                                             "updated_by": by})
        return await self.describe(entity_id)

    # --------------------------------------------------------------------- reads
    async def require(self, entity_id: str) -> dict:
        config = await self._store.get(self._entity(entity_id))
        if not config or not config.get("base_currency"):
            raise AccountingError(
                "CURRENCY_NOT_CONFIGURED",
                "لم تُحدَّد العملة الأساس والعملات المسموحة لهذه الجهة — العملة الأساس "
                "قرار صريح ولا تُستنتج من أول قيد", 409)
        return config

    async def base_currency(self, entity_id: str) -> str:
        return (await self.require(entity_id))["base_currency"]

    async def describe(self, entity_id: str) -> dict:
        entity_id = self._entity(entity_id)
        config = await self._store.get(entity_id)
        used = await self._journal.entity_currencies(entity_id)
        return {
            "entity_id": entity_id,
            "configured": bool(config and config.get("base_currency")),
            "base_currency": (config or {}).get("base_currency"),
            "currencies": (config or {}).get("currencies") or [],
            "currencies_with_history": used,
            "monetary_scale": DEFAULT_SCALE, "rate_scale": RATE_SCALE,
            "rules": {
                "new_postings": "configured + allowed + active",
                "history": "حركات عملة معطّلة تبقى مقروءة وتظهر في التقارير — التعطيل "
                           "يمنع العمليات الجديدة ولا يمحو التاريخ",
                "base_change": "BASE_CURRENCY_CHANGE_REQUIRES_MIGRATION عند وجود تاريخ",
                "mixing": "تقرير واحد = عملة واحدة؛ لا جمع ولا تحويل ضمني",
            },
        }

    # ------------------------------------------------------------------- the gate
    async def assert_allowed(self, entity_id: str, currency: str) -> None:
        """The async currency gate consulted by the central validator: it applies to EVERY
        posting path at once (journal, opening, reversal-through-posting, FX, year close).
        When an entity has no currency configuration, the static injected policy of Phase 3
        remains the only authority — existing behaviour is not changed silently."""
        config = await self._store.get(self._entity(entity_id))
        if not config or not config.get("base_currency"):
            return None
        code = self._code(currency)
        row = next((c for c in config.get("currencies") or []
                    if c["code"] == code), None)
        if not row:
            raise AccountingError(
                "CURRENCY_NOT_ALLOWED",
                f"العملة {code} غير مكوّنة لهذه الجهة — العملات المكوّنة: "
                f"{', '.join(c['code'] for c in config.get('currencies') or [])}")
        if not row.get("active", True):
            raise AccountingError(
                "CURRENCY_INACTIVE",
                f"العملة {code} معطّلة — لا تُقبل عمليات جديدة بها (تاريخها يبقى "
                f"مقروءاً في الأستاذ والتقارير)")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _entity(entity_id: str) -> str:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            raise AccountingError("ENTITY_REQUIRED", "الجهة المحاسبية مطلوبة")
        return entity_id

    @staticmethod
    def _code(currency: str) -> str:
        code = str(currency or "").strip().upper()
        if not 2 <= len(code) <= 8 or not code.isalpha():
            raise AccountingError("INVALID_CURRENCY",
                                  f"رمز عملة غير صالح: {currency!r}")
        return code
