"""Business ↔ Accounting RECONCILIATION — READ-ONLY DETECTION (ACC-016 cross-reference).

TRACEABILITY
  detection            ← Rahaal `/reconciliation` report            PORT + HARDEN
  `Fix All` / auto-post← Rahaal repair endpoints                    LEAVE (refused)

DETECT ≠ REPAIR. This module reports gaps; it never posts, never balances, never adjusts a
wallet and has no auto-fix. A financial repair needs its own approved workflow.
"""
from typing import Optional

from .events import FINANCIAL_EVENTS, build_source_key

ACCOUNTING_EVENTS = [e for e in FINANCIAL_EVENTS.values()
                     if e.posts_journal and e.implemented]


class BusinessAccountingReconciliation:
    def __init__(self, database, entity_id: str, journal_store, bridge):
        self._db = database
        self._entity = entity_id
        self._journal = journal_store
        self._bridge = bridge

    async def run(self, limit: int = 500, currency: Optional[str] = None) -> dict:
        sections, findings = [], []
        for spec, collection, id_field, status_match in (
            (FINANCIAL_EVENTS["wallet_topup"], "topups", "_id", {"status": "approved"}),
            (FINANCIAL_EVENTS["wallet_withdrawal"], "withdrawals", "_id",
             {"status": "approved"}),
            (FINANCIAL_EVENTS["b2b_transfer"], "transfers", "_id",
             {"status": "approved"}),
        ):
            docs = await self._db[collection].find(status_match) \
                .sort([("created_at", -1)]).to_list(length=min(limit, 1000))
            missing = []
            for doc in docs:
                key = build_source_key(self._entity, spec.business_object, spec.event,
                                       str(doc["_id"]))
                journal = await self._journal.find_by_source_key(self._entity, key)
                if not journal:
                    missing.append({"business_id": str(doc["_id"]),
                                    "amount": doc.get("amount"),
                                    "currency": doc.get("currency"),
                                    "source_key": key})
            sections.append({"event": spec.event, "label_ar": spec.label_ar,
                             "business_collection": collection,
                             "business_events": len(docs),
                             "missing_journals": len(missing)})
            if missing:
                findings.append({
                    "code": "BUSINESS_EVENT_WITHOUT_JOURNAL", "severity": "HIGH",
                    "event": spec.event,
                    "description": f"{len(missing)} حركة {spec.label_ar} بلا قيد محاسبي "
                                   f"متوقع",
                    "recommended_action": "أعد تنفيذ الأثر المحاسبي بنفس المفتاح "
                                          "(idempotent) — لا ترحيل تلقائي من هنا",
                    "reference": missing[:10]})

        # Journals produced by the integration whose business document no longer matches.
        orphans = []
        for spec in ACCOUNTING_EVENTS:
            journals = await self._journal.list_by_source_type(self._entity, spec.event)
            collection = {"topup": "topups", "withdrawal": "withdrawals",
                          "transfer": "transfers"}.get(spec.business_object)
            if not collection:
                continue
            for j in journals:
                if not j.get("source_id"):
                    orphans.append({"entry_no": j["entry_no"], "event": spec.event,
                                    "reason": "missing source_id"})
                    continue
                from bson import ObjectId
                try:
                    found = await self._db[collection].find_one(
                        {"_id": ObjectId(j["source_id"])}, {"_id": 1})
                except Exception:
                    found = None
                if not found:
                    orphans.append({"entry_no": j["entry_no"], "event": spec.event,
                                    "business_id": j["source_id"],
                                    "reason": "business document not found"})
        if orphans:
            findings.append({
                "code": "JOURNAL_WITHOUT_BUSINESS_REFERENCE", "severity": "HIGH",
                "description": f"{len(orphans)} قيد محاسبي بلا مرجع تجاري صالح",
                "recommended_action": "تحقيق يدوي — لا يُحذف قيد ولا يُعدَّل",
                "reference": orphans[:10]})

        duplicates = await self._journal.duplicate_source_keys(self._entity)
        if duplicates:
            findings.append({
                "code": "DUPLICATE_FINANCIAL_EFFECT", "severity": "CRITICAL",
                "description": f"{len(duplicates)} مفتاح عملية مكرر",
                "recommended_action": "تحقيق فوري — الفهرس الفريد يمنع تكراراً جديداً",
                "reference": duplicates[:10]})

        failures = await self._bridge.list_failures(limit=50)
        if failures:
            findings.append({
                "code": "ACCOUNTING_EFFECT_FAILED", "severity": "HIGH",
                "description": f"{len(failures)} أثر محاسبي فشل ترحيله بعد نجاح الأثر "
                               f"التجاري",
                "recommended_action": "صحّح السبب (ربط حساب/فترة مغلقة/عملة) ثم أعد "
                                      "المحاولة بنفس المفتاح",
                "reference": [{"event": f["event"], "error": f.get("error_code"),
                               "source_key": f["source_key"],
                               "attempts": f.get("attempts")} for f in failures[:10]]})

        return {"reconciliation": "business_vs_accounting", "entity_id": self._entity,
                "read_only": True, "repairs_performed": 0,
                "separation": "DETECT only — no auto-post, no auto-balance, no auto-repair",
                "sections": sections, "findings": findings,
                "healthy": not findings,
                "pending_accounting_failures": len(failures)}
