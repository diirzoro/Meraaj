"""Chart of Accounts service — the Phase 1 engine.

TRACEABILITY (Rahaal source → decision):
  seed_template()          ← lib/coa.js `seedCoaTemplate` + `seedTemplateRaw` + `stampVersion`   PORT
  audit_chart()            ← lib/coa.js `auditTenant` (structural part)                          PORT (financial-doc counts deferred)
  validate_chart()         ← lib/coa.js `validateTenant` (structural part)                       PORT (ledger/balance checks deferred)
  create_account()         ← route.js `POST /accounts` guards + `generateSubAccountCode`          PORT + HARDEN
  update_account()         ← route.js `PUT /accounts/:id` guards                                  PORT + HARDEN
  delete_account()         ← route.js `DELETE /accounts/:id` guards                               PORT + HARDEN
  build_tree()             ← route.js `GET /accounts/tree` (accounts part only)                   PORT (sub_entities = LEAVE)
  next_code()              ← route.js `GET /accounts/next-code`                                   PORT
  set_active()             ← NEW CORE REQUIREMENT (Rahaal had no account activation endpoint and
                             used two inconsistent field names: `inactive` and `is_active`)

Usage hook: `usage_counter` is an optional injected coroutine `(entity_id, code) -> int`
returning how many postings reference a code. Rahaal performed this check inline against
`journal_entries`. The journal does not exist yet in this module (Phase 2), so the hook
defaults to 0 while the guard itself is already wired and enforced — Phase 2 only supplies
the counter, it does not have to re-add the rule.
"""
import uuid
from typing import Optional, List, Callable, Awaitable

from .codegen import (generate_sub_account_code, preview_next_code, validate_manual_code,
                      assert_parent_can_have_children)
from .errors import AccountingError
from .models import AccountCreate, AccountUpdate, account_public
from .store import AccountStore, utc_now
from .template import ChartTemplate
from .types import AccountType, AccountOrigin, PROTECTED_ORIGINS, level_of_code

UsageCounter = Callable[[str, str], Awaitable[int]]


async def _no_usage(entity_id: str, code: str) -> int:
    return 0


class ChartOfAccounts:
    def __init__(self, store: AccountStore, template: ChartTemplate,
                 usage_counter: Optional[UsageCounter] = None):
        self.store = store
        self.template = template
        self._usage = usage_counter or _no_usage
        self._by_code = {a.code: a for a in template.accounts}

    # =============================================================== helpers
    def _template_row(self, code: str):
        return self._by_code.get(code)

    async def _require_entity(self, entity_id: str) -> str:
        """Tenant isolation invariant: every Core operation is scoped to exactly one entity,
        and a missing scope is a programming error — never a silent global operation.
        PORT of Rahaal's hard rule: 'no global destructive op exists'."""
        if not entity_id or not str(entity_id).strip():
            raise AccountingError("accounting.entity_required",
                                  "الجهة المحاسبية (entity) مطلوبة", 400)
        return str(entity_id).strip()

    # ================================================================ seeding
    async def seed_template(self, entity_id: str, by: Optional[str] = None) -> dict:
        """PORT — Rahaal `seedCoaTemplate`: idempotent, refuses to run when the entity
        already holds accounts, seeds the whole template in ONE insert, and stamps the
        version. HARDEN: the version is stamped only AFTER structural validation passes
        (Rahaal stamped right after seeding in the new-tenant path)."""
        entity_id = await self._require_entity(entity_id)
        existing = await self.store.count_accounts(entity_id)
        if existing > 0:
            return {"seeded": False, "reason": "accounts already exist",
                    "existing": existing, "entity_id": entity_id}
        now = utc_now()
        docs = []
        for a in self.template.accounts:
            docs.append({
                "id": str(uuid.uuid4()),
                "entity_id": entity_id,
                "code": a.code,
                "name": a.name,
                "name_ar": a.name_ar,
                "type": a.type.value,
                "parent": a.parent,
                "level": level_of_code(a.code),
                "is_group": bool(a.is_group),
                "is_parent": bool(a.is_group),
                "origin": a.origin.value,
                "role": a.role,
                "is_active": True,
                "next_child_seq": 0,
                "notes": None,
                "created_at": now,
                "created_by": by or "system",
                "updated_at": now,
                "updated_by": by or "system",
            })
        await self.store.insert_many(docs)
        validation = await self.validate_chart(entity_id)
        if not validation["ok"]:
            raise AccountingError("coa.seed_validation_failed",
                                  "فشل التحقق بعد تهيئة الدليل: "
                                  + " | ".join(validation["problems"]), 500)
        await self.store.stamp_chart_version(entity_id, self.template.version,
                                             "seed", "success", by)
        return {"seeded": True, "accounts": len(docs), "entity_id": entity_id,
                "coa_version": self.template.version,
                "template": self.template.key}

    # =============================================================== reading
    async def list_accounts(self, entity_id: str, include_inactive: bool = True) -> List[dict]:
        entity_id = await self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id, include_inactive)
        return [account_public(r) for r in rows]

    async def get_account(self, entity_id: str, account_id: str) -> dict:
        entity_id = await self._require_entity(entity_id)
        doc = await self.store.get_by_id(entity_id, account_id)
        if not doc:
            raise AccountingError("coa.account_not_found", "الحساب غير موجود", 404)
        return account_public(doc)

    async def build_tree(self, entity_id: str, include_inactive: bool = True) -> List[dict]:
        """PORT — Rahaal `GET /accounts/tree`: build a code-keyed map, attach each node to
        its parent, and return the roots. LEAVE: Rahaal also attached `sub_entities`
        (clients/suppliers/boxes) to the tree — those are business parties and have no place
        in a generic Core; generic account linking arrives in a later phase."""
        entity_id = await self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id, include_inactive)
        by_code, roots = {}, []
        for r in rows:
            by_code[r["code"]] = {**account_public(r), "children": []}
        for r in rows:
            node = by_code[r["code"]]
            parent = r.get("parent")
            if parent and parent in by_code:
                by_code[parent]["children"].append(node)
            else:
                roots.append(node)
        for node in by_code.values():
            node["children"].sort(key=lambda n: n["code"])
        roots.sort(key=lambda n: n["code"])
        return roots

    async def next_code(self, entity_id: str, parent_code: str) -> dict:
        entity_id = await self._require_entity(entity_id)
        code = await preview_next_code(self.store, entity_id, parent_code)
        return {"next_code": code, "parent": parent_code, "preview": True}

    # =============================================================== writing
    async def create_account(self, entity_id: str, payload: AccountCreate,
                             by: Optional[str] = None) -> dict:
        """PORT — every guard of Rahaal `POST /accounts`, in the same order:
          1. name + type required                              (Rahaal: name_ar && type)
          2. type must be one of the five accounting types
          3. parent must exist
          4. parent must not be an L4 terminal account
          5. parent must be a GROUP account (Rahaal BLOCKER-2 backend guard)
          6. child type must equal the parent's type
          7. manual code: digits, parent prefix, exact level length, unique
          8. no code supplied → atomic generation under the parent
        HARDEN (documented deviations):
          • the parent must also be ACTIVE (Rahaal had no usable active flag on accounts)
          • user-created accounts are always stamped origin=CUSTOM, so template/system
            accounts can never be impersonated
        """
        entity_id = await self._require_entity(entity_id)
        name = payload.name.strip()
        if not name:
            raise AccountingError("coa.name_required", "اسم الحساب مطلوب")
        if not isinstance(payload.type, AccountType):
            raise AccountingError(
                "coa.invalid_type",
                "نوع الحساب غير صالح — الأنواع المسموحة: أصول، خصوم، حقوق ملكية، "
                "إيرادات، مصروفات")

        parent_code = payload.parent
        parent = None
        if parent_code:
            parent = await self.store.get_by_code(entity_id, parent_code)
            if not parent:
                raise AccountingError("coa.parent_not_found",
                                      "الحساب الأب غير موجود", 404)
            assert_parent_can_have_children(parent_code)
            if not parent.get("is_group"):
                raise AccountingError(
                    "coa.parent_not_group",
                    f"الحساب الأب {parent_code} ليس حساب مجموعة (Group) — لا يمكن إنشاء "
                    f"حسابات فرعية إلا تحت حسابات المجموعات")
            if parent.get("is_active") is False:
                raise AccountingError(
                    "coa.parent_inactive",
                    f"الحساب الأب {parent_code} غير نشط — لا يمكن إنشاء حسابات تحته")
            if parent.get("type") != payload.type.value:
                raise AccountingError(
                    "coa.type_mismatch_parent",
                    f"نوع الحساب يجب أن يطابق نوع الأب ({parent.get('type')})")

        code = payload.code
        seq = None
        if not code:
            if not parent_code:
                raise AccountingError(
                    "coa.code_required",
                    "الرمز مطلوب — أو حدد الحساب الأب ليُولَّد الرمز تلقائياً")
            code, seq = await generate_sub_account_code(self.store, entity_id, parent_code)
        else:
            validate_manual_code(code, parent_code)
            if await self.store.code_exists(entity_id, code):
                raise AccountingError(
                    "coa.duplicate_code",
                    f"رمز الحساب \"{code}\" مستخدم بالفعل في هذه الجهة", 409)

        now = utc_now()
        doc = {
            "id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "code": code,
            "name": name,
            "name_ar": (payload.name_ar or name).strip(),
            "type": payload.type.value,
            "parent": parent_code,
            "level": level_of_code(code),
            "is_group": bool(payload.is_group),
            "is_parent": bool(payload.is_group),
            "origin": AccountOrigin.CUSTOM.value,
            "role": None,
            "is_active": True,
            "next_child_seq": 0,
            "notes": payload.notes,
            "created_at": now,
            "created_by": by,
            "updated_at": now,
            "updated_by": by,
        }
        if seq is not None:
            doc["account_seq"] = seq
        await self.store.insert(doc)
        return account_public(doc)

    async def update_account(self, entity_id: str, account_id: str,
                             payload: AccountUpdate, by: Optional[str] = None) -> dict:
        """PORT — Rahaal `PUT /accounts/:id`:
          • only name/type/parent/is_group/notes are updatable
          • the code is NEVER editable
          • system accounts: type/parent/is_group locked
        HARDEN:
          • the structural lock covers STANDARD template accounts too (Rahaal protected
            only 3103, so a user could restructure the template)
          • type/parent/is_group are locked once the account HAS CHILDREN or HAS POSTINGS
            (Rahaal allowed changing the type of an account with thousands of entries,
            silently distorting historical reports)
          • a re-parent is re-validated against every hierarchy rule, and is rejected when
            it would break the code-prefix invariant (the code cannot change, so the new
            parent must be the existing code's real prefix)
        """
        entity_id = await self._require_entity(entity_id)
        acc = await self.store.get_by_id(entity_id, account_id)
        if not acc:
            raise AccountingError("coa.account_not_found", "الحساب غير موجود", 404)

        fields = {}
        if payload.name is not None:
            fields["name"] = payload.name.strip()
        if payload.name_ar is not None:
            fields["name_ar"] = payload.name_ar.strip()
        if payload.notes is not None:
            fields["notes"] = payload.notes

        structural = {k: v for k, v in (("type", payload.type),
                                        ("parent", payload.parent),
                                        ("is_group", payload.is_group)) if v is not None}
        if structural:
            origin = AccountOrigin(acc.get("origin", AccountOrigin.CUSTOM.value))
            if origin in PROTECTED_ORIGINS:
                label = "نظامي" if origin == AccountOrigin.SYSTEM else "قياسي"
                raise AccountingError(
                    "coa.protected_structure",
                    f"الحساب {acc['code']} حساب {label} — لا يمكن تغيير نوعه أو موقعه "
                    f"في الشجرة أو تصنيفه")
            children = await self.store.count_children(entity_id, acc["code"])
            if children > 0:
                raise AccountingError(
                    "coa.has_children",
                    f"لا يمكن تغيير بنية الحساب — يحتوي على {children} حساب فرعي")
            postings = await self._usage(entity_id, acc["code"])
            if postings > 0:
                raise AccountingError(
                    "coa.has_postings",
                    f"لا يمكن تغيير بنية الحساب — مستخدم في {postings} قيد محاسبي")

            if "type" in structural:
                fields["type"] = structural["type"].value
            if "is_group" in structural:
                fields["is_group"] = bool(structural["is_group"])
            if "parent" in structural:
                new_parent = structural["parent"]
                parent_doc = await self.store.get_by_code(entity_id, new_parent)
                if not parent_doc:
                    raise AccountingError("coa.parent_not_found",
                                          "الحساب الأب غير موجود", 404)
                assert_parent_can_have_children(new_parent)
                if not parent_doc.get("is_group"):
                    raise AccountingError(
                        "coa.parent_not_group",
                        f"الحساب الأب {new_parent} ليس حساب مجموعة (Group)")
                target_type = fields.get("type", acc["type"])
                if parent_doc.get("type") != target_type:
                    raise AccountingError(
                        "coa.type_mismatch_parent",
                        f"نوع الحساب يجب أن يطابق نوع الأب ({parent_doc.get('type')})")
                # The code is immutable, so the new parent MUST be the code's real prefix —
                # otherwise the chart would contain a permanent prefix violation.
                validate_manual_code(acc["code"], new_parent)
                fields["parent"] = new_parent

        if not fields:
            return account_public(acc)
        fields["updated_at"] = utc_now()
        fields["updated_by"] = by
        updated = await self.store.update_fields(entity_id, account_id, fields)
        return account_public(updated)

    async def set_active(self, entity_id: str, account_id: str, active: bool,
                         by: Optional[str] = None) -> dict:
        """NEW CORE REQUIREMENT (declared, not silently invented).

        Rahaal had no account activation path and used two different field names for the
        same idea (`inactive` on parties, `is_active` checked on an account during the
        year-close preflight). The Core adopts ONE concept: `is_active`.

        Rules:
          • a SYSTEM account can never be deactivated (the engine posts to it)
          • deactivating a GROUP with active children is refused (it would hide a live
            subtree from the chart)
          • reactivating requires an active parent
          • deactivation never deletes history; blocking NEW postings on an inactive
            account is wired in the journal phase
        """
        entity_id = await self._require_entity(entity_id)
        acc = await self.store.get_by_id(entity_id, account_id)
        if not acc:
            raise AccountingError("coa.account_not_found", "الحساب غير موجود", 404)
        if bool(acc.get("is_active", True)) == active:
            return account_public(acc)
        if not active:
            if acc.get("origin") == AccountOrigin.SYSTEM.value:
                raise AccountingError(
                    "coa.system_account_protected",
                    f"الحساب {acc['code']} — {acc.get('name_ar')} حساب نظامي ولا يمكن "
                    f"تعطيله")
            active_children = await self.store.accounts.count_documents(
                {"entity_id": entity_id, "parent": acc["code"], "is_active": True})
            if active_children > 0:
                raise AccountingError(
                    "coa.has_active_children",
                    f"لا يمكن تعطيل الحساب — يحتوي على {active_children} حساب فرعي نشط")
        else:
            parent = acc.get("parent")
            if parent:
                parent_doc = await self.store.get_by_code(entity_id, parent)
                if parent_doc and parent_doc.get("is_active") is False:
                    raise AccountingError(
                        "coa.parent_inactive",
                        f"لا يمكن تنشيط الحساب — الحساب الأب {parent} غير نشط")
        updated = await self.store.update_fields(
            entity_id, account_id,
            {"is_active": active, "updated_at": utc_now(), "updated_by": by})
        return account_public(updated)

    async def delete_account(self, entity_id: str, account_id: str) -> dict:
        """PORT — Rahaal `DELETE /accounts/:id`: refuse for system accounts, refuse when the
        account has children, refuse when the account is referenced by any journal line.
        HARDEN: STANDARD template accounts are refused too (Rahaal protected only 3103, so
        Retained Earnings could be deleted and year-closing would then fail its preflight).
        """
        entity_id = await self._require_entity(entity_id)
        acc = await self.store.get_by_id(entity_id, account_id)
        if not acc:
            raise AccountingError("coa.account_not_found", "الحساب غير موجود", 404)
        origin = AccountOrigin(acc.get("origin", AccountOrigin.CUSTOM.value))
        if origin in PROTECTED_ORIGINS:
            label = "نظامي" if origin == AccountOrigin.SYSTEM else "قياسي (من القالب)"
            raise AccountingError(
                "coa.protected_account",
                f"الحساب {acc['code']} — {acc.get('name_ar')} حساب {label} ولا يمكن حذفه")
        children = await self.store.count_children(entity_id, acc["code"])
        if children > 0:
            raise AccountingError("coa.has_children",
                                  f"لا يمكن حذف الحساب — يحتوي على {children} حساب فرعي")
        postings = await self._usage(entity_id, acc["code"])
        if postings > 0:
            raise AccountingError("coa.has_postings",
                                  f"لا يمكن حذف الحساب — مستخدم في {postings} قيد محاسبي")
        await self.store.delete(entity_id, account_id)
        return {"deleted": True, "code": acc["code"]}

    # ====================================================== audit & validate
    async def audit_chart(self, entity_id: str) -> dict:
        """PORT — Rahaal `auditTenant`, structural half, check for check:
        duplicates, missing template codes, extras, wrong parent, wrong type, wrong
        is_group, orphans, hard orphans (parent not even in the template), cycles, plus a
        final `classification`.
        DEFERRED (Phase 2+): the financial-document counts and the ledger `unknownLineCodes`
        scan — there is no journal in this module yet, so counting it would be fiction.
        """
        entity_id = await self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id)
        settings = await self.store.get_settings(entity_id)

        by_code, duplicates = {}, []
        for a in rows:
            if a["code"] in by_code:
                duplicates.append(a["code"])
            by_code[a["code"]] = a
        codes = set(by_code)

        missing = [t.code for t in self.template.accounts if t.code not in codes]
        extras = [a["code"] for a in rows if a["code"] not in self._by_code]
        wrong_parent, wrong_type, wrong_group = [], [], []
        for a in rows:
            t = self._template_row(a["code"])
            if not t:
                continue
            if (a.get("parent") or None) != t.parent:
                wrong_parent.append(f"{a['code']}({a.get('parent') or '-'}"
                                    f"≠{t.parent or '-'})")
            if a.get("type") != t.type.value:
                wrong_type.append(a["code"])
            if bool(a.get("is_group")) != bool(t.is_group):
                wrong_group.append(a["code"])

        orphans = [a["code"] for a in rows
                   if a.get("parent") and a["parent"] not in by_code]
        hard_orphans = [a["code"] for a in rows
                        if a.get("parent") and a["parent"] not in by_code
                        and a["parent"] not in self._by_code]

        # PORT — Rahaal cycle detection (walk up the parents, stop on a repeat).
        cycles = []
        for a in rows:
            seen, cur = set(), a
            while cur and cur.get("parent"):
                if cur["code"] in seen:
                    cycles.append(a["code"])
                    break
                seen.add(cur["code"])
                cur = by_code.get(cur["parent"])

        prefix_violations = [f"{a['code']}!~{a['parent']}" for a in rows
                             if a.get("parent") and not a["code"].startswith(a["parent"])]
        level_mismatch = [a["code"] for a in rows
                          if a.get("level") != level_of_code(a["code"])]

        matches_template = not (missing or extras or wrong_parent or wrong_type
                                or wrong_group or duplicates or orphans or cycles)
        structural_anomaly = bool(duplicates or cycles or hard_orphans
                                  or prefix_violations or level_mismatch)

        if not rows:
            classification = "empty"
        elif settings and settings.get("coa_version") == self.template.version \
                and matches_template:
            classification = "already_current"
        elif matches_template and len(rows) == len(self.template.accounts):
            classification = "already_current"   # correct tree, only the stamp is missing
        elif structural_anomaly:
            classification = "manual_review"
        else:
            classification = "structure_mismatch"

        return {
            "entity_id": entity_id,
            "coa_version": (settings or {}).get("coa_version"),
            "template": self.template.key,
            "template_version": self.template.version,
            "account_count": len(rows),
            "custom_count": len([a for a in rows
                                 if a.get("origin") == AccountOrigin.CUSTOM.value]),
            "inactive_count": len([a for a in rows if a.get("is_active") is False]),
            "missing": missing, "extras": extras, "wrongParent": wrong_parent,
            "wrongType": wrong_type, "wrongGroup": wrong_group,
            "duplicates": duplicates, "orphans": orphans, "hardOrphans": hard_orphans,
            "cycles": cycles, "prefixViolations": prefix_violations,
            "levelMismatch": level_mismatch,
            "matchesTemplate": matches_template,
            "classification": classification,
            "deferred_checks": ["financial_document_counts", "ledger_unknown_line_codes",
                                "cached_balance_reconciliation", "trial_balance"],
        }

    async def validate_chart(self, entity_id: str) -> dict:
        """PORT — Rahaal `validateTenant`, structural half: missing/duplicate/orphan/cycle,
        wrong parent/type/is_group, the per-account PREFIX rule, and the system-account flag
        check (Rahaal asserted `3103.is_system`; here every SYSTEM role is asserted to exist,
        to be a posting leaf and to be flagged system).
        DEFERRED (Phase 2+): party placement/7-digit codes, cached-vs-ledger balance
        comparison and the per-currency trial balance — all of them need the journal.
        """
        entity_id = await self._require_entity(entity_id)
        audit = await self.audit_chart(entity_id)
        problems = []
        if audit["missing"]:
            problems.append(f"missing template codes: {','.join(audit['missing'])}")
        if audit["duplicates"]:
            problems.append(f"duplicate codes: {','.join(audit['duplicates'])}")
        if audit["orphans"]:
            problems.append(f"orphan accounts: {','.join(audit['orphans'])}")
        if audit["cycles"]:
            problems.append(f"cycles at: {','.join(audit['cycles'])}")
        if audit["wrongParent"]:
            problems.append(f"wrong parents: {','.join(audit['wrongParent'])}")
        if audit["wrongType"]:
            problems.append(f"wrong types: {','.join(audit['wrongType'])}")
        if audit["wrongGroup"]:
            problems.append(f"wrong is_group: {','.join(audit['wrongGroup'])}")
        if audit["prefixViolations"]:
            problems.append(f"prefix violations: {','.join(audit['prefixViolations'])}")
        if audit["levelMismatch"]:
            problems.append(f"level mismatch: {','.join(audit['levelMismatch'])}")

        rows = await self.store.list_all(entity_id)
        by_code = {a["code"]: a for a in rows}
        for t in self.template.accounts:
            if t.origin != AccountOrigin.SYSTEM:
                continue
            a = by_code.get(t.code)
            if not a:
                problems.append(f"system account {t.code} ({t.role}) is missing")
                continue
            if a.get("origin") != AccountOrigin.SYSTEM.value:
                problems.append(f"{t.code} is not flagged origin=system")
            if a.get("is_group"):
                problems.append(f"system account {t.code} must be a posting (leaf) account")
            if a.get("is_active") is False:
                problems.append(f"system account {t.code} is inactive")
        return {"ok": not problems, "problems": problems,
                "classification": audit["classification"], "entity_id": entity_id}
