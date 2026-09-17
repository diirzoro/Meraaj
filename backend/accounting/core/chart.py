"""Chart of Accounts service — Phase 1 foundation + Phase 2 management/guards/lifecycle.

TRACEABILITY (Meraaj function ← Rahaal source → decision)
  seed_template()       ← lib/coa.js `seedCoaTemplate` + `seedTemplateRaw` + `stampVersion`   PORT + HARDEN
  audit_chart()         ← lib/coa.js `auditTenant` (structural half)                           PORT + HARDEN
  validate_chart()      ← lib/coa.js `validateTenant` (structural half)                        PORT
  create_account()      ← route.js `POST /accounts` guards + `generateSubAccountCode`           PORT + HARDEN
  update_account()      ← route.js `PUT /accounts/:id` guards                                   PORT + HARDEN
  delete_account()      ← route.js `DELETE /accounts/:id` guards                                PORT + HARDEN
  build_tree()          ← route.js `GET /accounts/tree` (accounts part only)                    PORT (sub_entities = LEAVE)
  next_code()           ← route.js `GET /accounts/next-code`                                    PORT
  find_by_code()        ← route.js `accounts.findOne({tenant_id, code})`                        PORT
  find_by_role()        ← lib/coa.js `C` canonical-code map                                     ADAPT (role instead of number)
  set_active()          ← (no Rahaal equivalent)                                                NEW CORE REQUIREMENT
  usage probe boundary  ← route.js inline `journal_entries` count                               DEFERRED (contract only)
"""
import uuid
from typing import Optional, List

from .audit import ChartAuditor
from .codegen import (generate_sub_account_code, preview_next_code, validate_manual_code,
                      assert_parent_can_have_children,
                      sync_parent_sequence_after_manual_code)
from .errors import AccountingError
from .models import AccountCreate, AccountUpdate, account_public
from .store import AccountStore, utc_now
from .template import ChartTemplate
from .types import AccountType, AccountOrigin, PROTECTED_ORIGINS, level_of_code
from .usage import NULL_USAGE_PROBE, UsageProbe


class ChartOfAccounts:
    def __init__(self, store: AccountStore, template: ChartTemplate,
                 usage_probe: Optional[UsageProbe] = None):
        self.store = store
        self.template = template
        # Phase 2 ships the null probe on purpose: no guard may claim to have inspected a
        # journal that does not exist. A later phase injects a real probe here and every
        # guard below starts enforcing posting history without being rewritten.
        self.usage = usage_probe or NULL_USAGE_PROBE
        self.auditor = ChartAuditor(template)
        self._by_code = {a.code: a for a in template.accounts}

    # =============================================================== helpers
    @staticmethod
    def _require_entity(entity_id: str) -> str:
        """Tenant isolation invariant: every Core operation is scoped to exactly one
        entity, and a missing scope is a programming error — never a silent global
        operation. PORT of Rahaal's hard rule: 'no global destructive op exists'."""
        if not entity_id or not str(entity_id).strip():
            raise AccountingError("accounting.entity_required",
                                  "الجهة المحاسبية (entity) مطلوبة", 400)
        return str(entity_id).strip()

    async def _get_or_404(self, entity_id: str, account_id: str) -> dict:
        doc = await self.store.get_by_id(entity_id, account_id)
        if not doc:
            # Also the cross-entity answer: an id from another entity is simply not found.
            raise AccountingError("coa.account_not_found", "الحساب غير موجود", 404)
        return doc

    async def _assert_usable_parent(self, entity_id: str, parent_code: str,
                                    child_type: str) -> dict:
        """The single parent gate shared by create and re-parent.

        PORT — Rahaal `POST /accounts`: parent must exist, must not be an L4 terminal, must
        be a GROUP (its BLOCKER-2 backend fix), and the child's type must equal the
        parent's type.
        HARDEN — the parent must also be ACTIVE (Rahaal had no usable active flag).
        Entity isolation: the parent is looked up INSIDE the entity, so a parent code that
        exists only in another entity is reported as missing.
        """
        parent = await self.store.get_by_code(entity_id, parent_code)
        if not parent:
            raise AccountingError("coa.parent_not_found",
                                  f"الحساب الأب {parent_code} غير موجود في هذه الجهة", 404)
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
        if parent.get("type") != child_type:
            raise AccountingError(
                "coa.type_mismatch_parent",
                f"نوع الحساب يجب أن يطابق نوع الأب ({parent.get('type')})")
        return parent

    async def _assert_structural_change_allowed(self, entity_id: str, acc: dict) -> None:
        """Gate for any change to `type` / `parent` / `is_group`.

        PORT — Rahaal locked these for its single `is_system` account.
        HARDEN — the lock covers STANDARD template accounts too, and additionally refuses
        while the account HAS CHILDREN (Rahaal allowed restructuring a live subtree).
        DEFERRED — posting history: the probe is consulted only when it is available, so the
        error message never claims a journal was inspected when there is none.
        """
        origin = self._origin_of(acc)
        if origin in PROTECTED_ORIGINS:
            label = "نظامي" if origin == AccountOrigin.SYSTEM else "قياسي"
            raise AccountingError(
                "coa.protected_structure",
                f"الحساب {acc['code']} حساب {label} — لا يمكن تغيير نوعه أو موقعه في "
                f"الشجرة أو تصنيفه")
        children = await self.store.count_children(entity_id, acc["code"])
        if children > 0:
            raise AccountingError("coa.has_children",
                                  f"لا يمكن تغيير بنية الحساب — يحتوي على {children} "
                                  f"حساب فرعي")
        if self.usage.available:
            postings = await self.usage.count_postings(entity_id, acc["code"])
            if postings > 0:
                raise AccountingError("coa.has_postings",
                                      f"لا يمكن تغيير بنية الحساب — مستخدم في {postings} "
                                      f"قيد محاسبي")

    @staticmethod
    def _origin_of(acc: dict) -> AccountOrigin:
        try:
            return AccountOrigin(acc.get("origin", AccountOrigin.CUSTOM.value))
        except ValueError:
            # An unreadable origin is treated as maximally protected, and the structural
            # audit reports it under `invalidOrigin`.
            return AccountOrigin.SYSTEM

    # ================================================================ seeding
    async def seed_template(self, entity_id: str, by: Optional[str] = None) -> dict:
        """PORT — Rahaal `seedCoaTemplate`: EXPLICIT only, idempotent, refuses to run when
        the entity already holds accounts, seeds the whole template in one insert, then
        stamps the version.
        HARDEN — the stamp happens only AFTER structural validation passes (Rahaal stamped
        straight after seeding in the new-tenant path).
        Hard rule: never reset, never replace, never delete, never migrate. An entity whose
        state is unclear is classified for human review and left untouched.
        """
        entity_id = self._require_entity(entity_id)
        existing = await self.store.count_accounts(entity_id)
        if existing > 0:
            state = await self.audit_chart(entity_id)
            return {"seeded": False,
                    "reason": "accounts already exist — nothing was changed",
                    "existing": existing, "entity_id": entity_id,
                    "classification": state["classification"],
                    "stamped_version": state["coa_version"],
                    "template_version": self.template.version,
                    "auto_repair": False,
                    "next_step": ("review the audit report and decide manually"
                                  if state["classification"] not in
                                  ("already_current", "custom_extended")
                                  else "nothing to do")}
        now = utc_now()
        docs = [{
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
        } for a in self.template.accounts]
        await self.store.insert_many(docs)
        validation = await self.validate_chart(entity_id)
        if not validation["ok"]:
            raise AccountingError("coa.seed_validation_failed",
                                  "فشل التحقق بعد تهيئة الدليل: "
                                  + " | ".join(validation["problems"]), 500)
        await self.store.stamp_chart_version(entity_id, self.template.version,
                                             "seed", "success", by)
        return {"seeded": True, "accounts": len(docs), "entity_id": entity_id,
                "coa_version": self.template.version, "template": self.template.key,
                "classification": "already_current"}

    # =============================================================== reading
    async def list_accounts(self, entity_id: str, include_inactive: bool = True) -> List[dict]:
        entity_id = self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id, include_inactive)
        return [account_public(r) for r in rows]

    async def get_account(self, entity_id: str, account_id: str) -> dict:
        """Lookup by STABLE ID (never by name — a name is a label, not an identifier)."""
        entity_id = self._require_entity(entity_id)
        return account_public(await self._get_or_404(entity_id, account_id))

    async def find_by_code(self, entity_id: str, code: str) -> dict:
        """PORT — Rahaal `accounts.findOne({ tenant_id, code })`, entity-scoped."""
        entity_id = self._require_entity(entity_id)
        doc = await self.store.get_by_code(entity_id, str(code).strip())
        if not doc:
            raise AccountingError("coa.account_not_found",
                                  f"لا يوجد حساب بالرمز {code} في هذه الجهة", 404)
        return account_public(doc)

    async def find_by_role(self, entity_id: str, role: str) -> dict:
        """ADAPT — replaces Rahaal's hardcoded canonical-code map `C`.

        Business logic asks for a ROLE ("the retained-earnings account") and never for a
        number, so a project can renumber its chart without touching any logic. The role is
        resolved against the live chart of THIS entity, and the row must still match the
        template's type/leaf expectation for that role.
        """
        entity_id = self._require_entity(entity_id)
        role = str(role).strip()
        expected = self.template.by_role(role)
        if not expected:
            raise AccountingError("coa.unknown_role",
                                  f"الدور المحاسبي '{role}' غير معروف في هذا القالب", 400)
        doc = await self.store.find_one_by_role(entity_id, role)
        if not doc:
            raise AccountingError(
                "coa.role_not_assigned",
                f"الدور المحاسبي '{role}' غير مرتبط بأي حساب في هذه الجهة", 404)
        if doc.get("type") != expected.type.value \
                or bool(doc.get("is_group")) != bool(expected.is_group):
            raise AccountingError(
                "coa.role_integrity_violation",
                f"الحساب المرتبط بالدور '{role}' ({doc.get('code')}) لا يطابق نوع/تصنيف "
                f"الدور في القالب — راجع تقرير التدقيق البنيوي", 409)
        if doc.get("is_active") is False:
            raise AccountingError(
                "coa.role_account_inactive",
                f"الحساب المرتبط بالدور '{role}' ({doc.get('code')}) غير نشط", 409)
        return account_public(doc)

    async def build_tree(self, entity_id: str, include_inactive: bool = True) -> List[dict]:
        """PORT — Rahaal `GET /accounts/tree`: build a code-keyed map, attach every node to
        its parent, return the roots, ordered deterministically by account code.
        LEAVE — Rahaal also attached `sub_entities` (clients/suppliers/boxes). Those are
        business parties and have no place in a generic Core; generic account linking
        arrives in its own phase.
        """
        entity_id = self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id, include_inactive)
        by_code = {r["code"]: {**account_public(r), "children": []} for r in rows}
        roots = []
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
        entity_id = self._require_entity(entity_id)
        code = await preview_next_code(self.store, entity_id, parent_code)
        return {"next_code": code, "parent": parent_code, "preview": True}

    # =============================================================== creating
    async def create_account(self, entity_id: str, payload: AccountCreate,
                             by: Optional[str] = None) -> dict:
        """PORT — every guard of Rahaal `POST /accounts`, in its original order:
          1. name + type required                      (Rahaal: name_ar && type)
          2. type is one of the five accounting types
          3. parent exists  4. parent is not an L4 terminal  5. parent is a GROUP
          6. child type equals the parent's type
          7. manual code: digits, parent prefix, exact level length, unique
          8. no code supplied → atomic allocation under the parent
        HARDEN:
          • the parent must be ACTIVE and must live in the SAME entity
          • a user-created account is always stamped origin=CUSTOM with role=None, so
            SYSTEM/STANDARD accounts and semantic roles can never be impersonated
          • a manual code raises the parent counter when it overtakes it (see codegen)
        """
        entity_id = self._require_entity(entity_id)
        name = payload.name.strip()
        if not name:
            raise AccountingError("coa.name_required", "اسم الحساب مطلوب")
        if not isinstance(payload.type, AccountType):
            raise AccountingError(
                "coa.invalid_type",
                "نوع الحساب غير صالح — الأنواع المسموحة: أصول، خصوم، حقوق ملكية، "
                "إيرادات، مصروفات")

        parent_code = payload.parent
        if parent_code:
            await self._assert_usable_parent(entity_id, parent_code, payload.type.value)

        code, seq = payload.code, None
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
        if payload.code:
            await sync_parent_sequence_after_manual_code(self.store, entity_id,
                                                         parent_code, code)
        return account_public(doc)

    # =============================================================== updating
    async def update_account(self, entity_id: str, account_id: str,
                             payload: AccountUpdate, by: Optional[str] = None) -> dict:
        """PORT — Rahaal `PUT /accounts/:id`: only name/type/parent/is_group/notes are
        updatable and the CODE is never editable.

        Immutable by construction (rejected at the schema boundary, see models.py):
        `id`, `entity_id`, `code`, `origin`, `level`, `role`, `next_child_seq`, created
        metadata — and `is_active`, which has its own lifecycle path.

        Freely updatable: `name`, `name_ar`, `notes`.
        Structurally gated: `type`, `parent`, `is_group` (see _assert_structural_change_allowed).
        """
        entity_id = self._require_entity(entity_id)
        acc = await self._get_or_404(entity_id, account_id)

        fields = {}
        if payload.name is not None:
            new_name = payload.name.strip()
            if not new_name:
                raise AccountingError("coa.name_required", "اسم الحساب مطلوب")
            fields["name"] = new_name
        if payload.name_ar is not None:
            fields["name_ar"] = payload.name_ar.strip()
        if payload.notes is not None:
            fields["notes"] = payload.notes

        structural = {k: v for k, v in (("type", payload.type),
                                        ("parent", payload.parent),
                                        ("is_group", payload.is_group)) if v is not None}
        if structural:
            await self._assert_structural_change_allowed(entity_id, acc)
            if "type" in structural:
                fields["type"] = structural["type"].value
            if "is_group" in structural:
                new_is_group = bool(structural["is_group"])
                if not new_is_group and int(acc.get("next_child_seq") or 0) > 0:
                    # The counter is never lowered and its numbers are never re-used, so a
                    # group that has already allocated children cannot be demoted to a leaf.
                    raise AccountingError(
                        "coa.group_already_allocated",
                        f"لا يمكن تحويل الحساب {acc['code']} إلى حساب ترحيل — سبق أن "
                        f"وُلّدت تحته أرقام فرعية")
                fields["is_group"] = new_is_group
                fields["is_parent"] = new_is_group
            # The parent gate runs for a re-parent AND for a type-only change: otherwise a
            # type edit could leave the account sitting under a differently-typed parent.
            target_parent = structural.get("parent", acc.get("parent"))
            target_type = fields.get("type", acc["type"])
            if target_parent:
                await self._assert_usable_parent(entity_id, target_parent, target_type)
                # The code is immutable, so the parent MUST be the code's real prefix,
                # otherwise the chart would carry a permanent prefix violation.
                validate_manual_code(acc["code"], target_parent)
            elif len(acc["code"]) != 1:
                raise AccountingError(
                    "coa.orphan_account",
                    f"الحساب {acc['code']} ليس حساباً جذرياً ولا يمكن أن يكون بلا أب")
            if "parent" in structural:
                fields["parent"] = structural["parent"]

        if not fields:
            return account_public(acc)
        fields["updated_at"] = utc_now()
        fields["updated_by"] = by
        return account_public(await self.store.update_fields(entity_id, account_id, fields))

    # ================================================= activate / deactivate
    async def set_active(self, entity_id: str, account_id: str, active: bool,
                         by: Optional[str] = None) -> dict:
        """NEW CORE REQUIREMENT (declared, not silently invented).

        Rahaal had no account activation path and used two different names for the same
        idea (`inactive` on business parties, `is_active` read during the year-close
        preflight). The Core adopts ONE concept: `is_active`.

        Deactivate:
          • a SYSTEM account can never be deactivated (the engine itself posts to it)
          • a parent with ACTIVE children is refused (it would hide a live subtree)
          • STANDARD accounts follow the Phase 1 policy: deactivation is allowed (it does
            not break the template — the row keeps its code, parent and place in the tree)
            and the structural audit reports it under `inactiveTemplateAccounts`
        Activate:
          • the parent must exist, be active, be a group, be the code's real prefix and
            share the account's type — i.e. the account may only come back into a tree
            position that is still structurally valid
        Nothing is ever deleted: an inactive account keeps its historical place in the tree.
        Blocking NEW postings on an inactive account belongs to the journal phase.
        """
        entity_id = self._require_entity(entity_id)
        acc = await self._get_or_404(entity_id, account_id)
        if bool(acc.get("is_active", True)) == active:
            return account_public(acc)

        if not active:
            if self._origin_of(acc) == AccountOrigin.SYSTEM:
                raise AccountingError(
                    "coa.system_account_protected",
                    f"الحساب {acc['code']} — {acc.get('name_ar')} حساب نظامي ولا يمكن تعطيله")
            active_children = await self.store.accounts.count_documents(
                {"entity_id": entity_id, "parent": acc["code"], "is_active": True})
            if active_children > 0:
                raise AccountingError(
                    "coa.has_active_children",
                    f"لا يمكن تعطيل الحساب — يحتوي على {active_children} حساب فرعي نشط")
        else:
            parent_code = acc.get("parent")
            if parent_code:
                # Re-validate the whole hierarchy before letting the account back in.
                await self._assert_usable_parent(entity_id, parent_code, acc["type"])
                validate_manual_code(acc["code"], parent_code)
            elif len(acc["code"]) != 1:
                raise AccountingError(
                    "coa.orphan_account",
                    f"لا يمكن تنشيط الحساب {acc['code']} — لا يملك حساباً أباً وليس حساباً "
                    f"جذرياً")
            if acc.get("level") != level_of_code(acc["code"]):
                raise AccountingError(
                    "coa.level_mismatch",
                    f"لا يمكن تنشيط الحساب {acc['code']} — مستواه المحفوظ لا يطابق رمزه؛ "
                    f"راجع تقرير التدقيق البنيوي")

        updated = await self.store.update_fields(
            entity_id, account_id,
            {"is_active": active, "updated_at": utc_now(), "updated_by": by})
        return account_public(updated)

    # =============================================================== deleting
    async def delete_account(self, entity_id: str, account_id: str,
                             by: Optional[str] = None) -> dict:
        """PORT — Rahaal `DELETE /accounts/:id`: refuse for system accounts, refuse when the
        account has children, refuse when it is referenced by a journal line.
        HARDEN — STANDARD template accounts are refused too (Rahaal protected only 3103, so
        Retained Earnings could be deleted and year-closing would then fail its preflight).
        DEFERRED — the journal check runs only when the usage probe is available; until then
        deletion is limited to a CUSTOM, childless account and no message pretends a
        journal was inspected.
        Deleting can never break the tree: an account with children is always refused, so no
        orphan can be produced.
        """
        entity_id = self._require_entity(entity_id)
        acc = await self._get_or_404(entity_id, account_id)
        origin = self._origin_of(acc)
        if origin in PROTECTED_ORIGINS:
            label = "نظامي" if origin == AccountOrigin.SYSTEM else "قياسي (من القالب)"
            raise AccountingError(
                "coa.protected_account",
                f"الحساب {acc['code']} — {acc.get('name_ar')} حساب {label} ولا يمكن حذفه")
        if acc.get("role"):
            raise AccountingError(
                "coa.role_bound_account",
                f"الحساب {acc['code']} مرتبط بدور محاسبي ({acc['role']}) ولا يمكن حذفه")
        children = await self.store.count_children(entity_id, acc["code"])
        if children > 0:
            raise AccountingError("coa.has_children",
                                  f"لا يمكن حذف الحساب — يحتوي على {children} حساب فرعي "
                                  f"(الحذف سيُفسد الشجرة)")
        if self.usage.available:
            postings = await self.usage.count_postings(entity_id, acc["code"])
            if postings > 0:
                raise AccountingError("coa.has_postings",
                                      f"لا يمكن حذف الحساب — مستخدم في {postings} قيد محاسبي")
        await self.store.delete(entity_id, account_id)
        # Sequence integrity: the parent counter is deliberately NOT lowered, so a deleted
        # child's number is never handed out again.
        return {"deleted": True, "code": acc["code"], "entity_id": entity_id,
                "sequence_rolled_back": False, "deleted_by": by}

    # ====================================================== audit & validate
    async def audit_chart(self, entity_id: str) -> dict:
        entity_id = self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id)
        settings = await self.store.get_settings(entity_id)
        return self.auditor.audit(entity_id, rows, settings)

    async def validate_chart(self, entity_id: str) -> dict:
        entity_id = self._require_entity(entity_id)
        rows = await self.store.list_all(entity_id)
        settings = await self.store.get_settings(entity_id)
        return self.auditor.validate(entity_id, rows, settings)
