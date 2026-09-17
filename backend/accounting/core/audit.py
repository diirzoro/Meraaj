"""Structural audit, validation and template-state classification.

TRACEABILITY
  ChartAuditor.audit()    ← Rahaal `lib/coa.js :: auditTenant`   PORT (structural half) + HARDEN
  ChartAuditor.validate() ← Rahaal `lib/coa.js :: validateTenant` PORT (structural half)
  classification          ← Rahaal `auditTenant.classification`  PORT + ADAPT (7 explicit states)

Phase 2 extends the Phase 1 structural audit with the checks Rahaal either did elsewhere or
did not have at all, and which are provable WITHOUT a journal:
  • children under a terminal L4 parent            (Rahaal enforced on write only → HARDEN: also detected on read)
  • invalid origin values                          (NEW — Rahaal had no origin classification)
  • role integrity: duplicates, roles on custom accounts, role/type or role/group mismatch
                                                    (NEW — Rahaal asserted only `3103.is_system`)
  • active child under an inactive parent          (NEW — Rahaal had no coherent active flag)
  • deactivated STANDARD/template accounts         (NEW)
  • sequence anomalies: `next_child_seq` behind the highest existing child suffix, a
    sequence on a non-group account, a sequence beyond its ceiling
                                                    (NEW — reported only, never repaired)

Hard rule preserved from Rahaal: the audit DIAGNOSES and never repairs.
Everything that needs the journal stays DEFERRED and is declared in the response.
"""
from typing import Optional

from .types import AccountOrigin, AccountType, level_of_code, SEQUENCE_CAP, sequence_pad
from .template import ChartTemplate

DEFERRED_CHECKS = [
    "journal_usage_per_account",
    "ledger_unknown_line_codes",
    "cached_balance_reconciliation",
    "trial_balance_per_currency",
    "party_account_placement",
]


class ChartAuditor:
    def __init__(self, template: ChartTemplate):
        self.template = template
        self._by_code = {a.code: a for a in template.accounts}
        self._role_codes = {a.role: a.code for a in template.accounts if a.role}

    # ------------------------------------------------------------------ audit
    def audit(self, entity_id: str, rows: list, settings: Optional[dict]) -> dict:
        by_code, duplicates = {}, []
        for a in rows:
            if a["code"] in by_code:
                duplicates.append(a["code"])
            by_code[a["code"]] = a
        codes = set(by_code)

        missing = [t.code for t in self.template.accounts if t.code not in codes]
        template_codes = set(self._by_code)
        extras = [a["code"] for a in rows if a["code"] not in template_codes]
        # ADAPT: Rahaal lumped every non-template account into `extras`. A user-created
        # CUSTOM account is a legitimate extension, not an anomaly, so the two are split.
        custom_extras = [a["code"] for a in rows
                         if a["code"] not in template_codes
                         and a.get("origin") == AccountOrigin.CUSTOM.value]
        unexpected_extras = [c for c in extras if c not in custom_extras]

        wrong_parent, wrong_type, wrong_group = [], [], []
        for a in rows:
            t = self._by_code.get(a["code"])
            if not t:
                continue
            if (a.get("parent") or None) != t.parent:
                wrong_parent.append(f"{a['code']}({a.get('parent') or '-'}≠{t.parent or '-'})")
            if a.get("type") != t.type.value:
                wrong_type.append(a["code"])
            if bool(a.get("is_group")) != bool(t.is_group):
                wrong_group.append(a["code"])

        orphans = [a["code"] for a in rows if a.get("parent") and a["parent"] not in by_code]
        hard_orphans = [a["code"] for a in rows
                        if a.get("parent") and a["parent"] not in by_code
                        and a["parent"] not in template_codes]

        # PORT — Rahaal cycle detection: walk up the parents and stop on a repeat.
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
                          if a.get("level") != self._safe_level(a["code"])]
        invalid_code_length = [a["code"] for a in rows if self._safe_level(a["code"]) is None]
        children_under_terminal = [a["code"] for a in rows
                                   if a.get("parent") and len(a["parent"]) >= 7]
        children_under_leaf = [a["code"] for a in rows
                               if a.get("parent") in by_code
                               and not by_code[a["parent"]].get("is_group")]

        valid_origins = {o.value for o in AccountOrigin}
        valid_types = {t.value for t in AccountType}
        invalid_origin = [a["code"] for a in rows if a.get("origin") not in valid_origins]
        invalid_type = [a["code"] for a in rows if a.get("type") not in valid_types]

        role_issues = self._role_issues(rows)
        active_under_inactive = [a["code"] for a in rows
                                 if a.get("is_active") is not False
                                 and a.get("parent") in by_code
                                 and by_code[a["parent"]].get("is_active") is False]
        inactive_template = [a["code"] for a in rows
                             if a.get("is_active") is False
                             and a.get("origin") in (AccountOrigin.STANDARD.value,
                                                     AccountOrigin.SYSTEM.value)]
        sequence_anomalies = self._sequence_anomalies(rows, by_code)

        stamped_version = (settings or {}).get("coa_version")
        template_identical = not (missing or unexpected_extras or wrong_parent or wrong_type
                                  or wrong_group or duplicates or orphans or cycles)
        inconsistent = bool(duplicates or cycles or hard_orphans or prefix_violations
                            or level_mismatch or invalid_code_length or invalid_origin
                            or invalid_type or children_under_terminal
                            or children_under_leaf or role_issues
                            or active_under_inactive)
        needs_review = bool(missing or unexpected_extras or wrong_parent or wrong_type
                            or wrong_group)

        classification = self._classify(
            rows=rows, stamped_version=stamped_version,
            template_version=self.template.version,
            template_identical=template_identical, inconsistent=inconsistent,
            needs_review=needs_review, has_custom=bool(custom_extras))

        return {
            "entity_id": entity_id,
            "coa_version": stamped_version,
            "template": self.template.key,
            "template_version": self.template.version,
            "account_count": len(rows),
            "template_account_count": len(self.template.accounts),
            "custom_count": len([a for a in rows
                                 if a.get("origin") == AccountOrigin.CUSTOM.value]),
            "inactive_count": len([a for a in rows if a.get("is_active") is False]),
            # Rahaal-equivalent keys (names kept so the two audits can be compared 1:1)
            "missing": missing,
            "extras": extras,
            "customExtras": custom_extras,
            "unexpectedExtras": unexpected_extras,
            "wrongParent": wrong_parent,
            "wrongType": wrong_type,
            "wrongGroup": wrong_group,
            "duplicates": duplicates,
            "orphans": orphans,
            "hardOrphans": hard_orphans,
            "cycles": cycles,
            # Phase 2 additions
            "prefixViolations": prefix_violations,
            "levelMismatch": level_mismatch,
            "invalidCodeLength": invalid_code_length,
            "childrenUnderTerminal": children_under_terminal,
            "childrenUnderLeaf": children_under_leaf,
            "invalidOrigin": invalid_origin,
            "invalidType": invalid_type,
            "roleIssues": role_issues,
            "activeUnderInactiveParent": active_under_inactive,
            "inactiveTemplateAccounts": inactive_template,
            "sequenceAnomalies": sequence_anomalies,
            "matchesTemplate": template_identical,
            "classification": classification,
            "auto_repair": False,
            "deferred_checks": DEFERRED_CHECKS,
        }

    # ------------------------------------------------------------- validation
    def validate(self, entity_id: str, rows: list, settings: Optional[dict]) -> dict:
        """Validate = a yes/no structural verdict (Audit = the detailed diagnosis).
        No auto-repair, and nothing here touches balances, journals or the ledger."""
        a = self.audit(entity_id, rows, settings)
        problems = []

        def add(key, label):
            if a[key]:
                problems.append(f"{label}: {','.join(str(x) for x in a[key])}")

        add("missing", "missing template codes")
        add("duplicates", "duplicate codes")
        add("orphans", "orphan accounts")
        add("hardOrphans", "hard orphans")
        add("cycles", "cycles")
        add("wrongParent", "wrong parents")
        add("wrongType", "wrong types")
        add("wrongGroup", "wrong is_group")
        add("prefixViolations", "prefix violations")
        add("levelMismatch", "level mismatch")
        add("invalidCodeLength", "invalid code length")
        add("childrenUnderTerminal", "children under terminal L4")
        add("childrenUnderLeaf", "children under a leaf account")
        add("invalidOrigin", "invalid origin")
        add("invalidType", "invalid type")
        add("roleIssues", "role integrity")
        add("activeUnderInactiveParent", "active child under inactive parent")
        add("unexpectedExtras", "unexpected non-template accounts")

        # PORT — Rahaal asserted `3103.is_system`. Generalised: EVERY system role must
        # exist, be flagged system, be a posting (leaf) account and be active.
        by_code = {r["code"]: r for r in rows}
        for t in self.template.accounts:
            if t.origin != AccountOrigin.SYSTEM:
                continue
            row = by_code.get(t.code)
            if not row:
                problems.append(f"system account {t.code} ({t.role}) is missing")
                continue
            if row.get("origin") != AccountOrigin.SYSTEM.value:
                problems.append(f"{t.code} is not flagged origin=system")
            if row.get("is_group"):
                problems.append(f"system account {t.code} must be a posting (leaf) account")
            if row.get("is_active") is False:
                problems.append(f"system account {t.code} is inactive")

        return {"ok": not problems, "problems": problems,
                "classification": a["classification"], "entity_id": entity_id,
                "auto_repair": False, "deferred_checks": DEFERRED_CHECKS}

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _safe_level(code: str) -> Optional[int]:
        try:
            return level_of_code(code)
        except Exception:
            return None

    def _role_issues(self, rows: list) -> list:
        """Role integrity (NEW): a role is a generic ACCOUNTING semantic handle.
        Rules: unique within the entity, only on template accounts, and consistent with the
        template's type and group/leaf nature for that role."""
        issues, seen = [], {}
        for a in rows:
            role = a.get("role")
            if not role:
                continue
            if role in seen:
                issues.append(f"duplicate role '{role}' on {seen[role]} and {a['code']}")
            seen[role] = a["code"]
            t = self.template.by_role(role)
            if not t:
                issues.append(f"unknown role '{role}' on {a['code']}")
                continue
            if a.get("origin") == AccountOrigin.CUSTOM.value:
                issues.append(f"custom account {a['code']} must not carry role '{role}'")
            if t.code != a["code"]:
                issues.append(f"role '{role}' expected on {t.code} but found on {a['code']}")
            if a.get("type") != t.type.value:
                issues.append(f"role '{role}' type mismatch on {a['code']}")
            if bool(a.get("is_group")) != bool(t.is_group):
                issues.append(f"role '{role}' group/leaf mismatch on {a['code']}")
        for role, code in self._role_codes.items():
            if role not in seen:
                issues.append(f"role '{role}' ({code}) is not assigned to any account")
        return issues

    @staticmethod
    def _sequence_anomalies(rows: list, by_code: dict) -> list:
        """Sequence integrity, DETECTED ONLY — never repaired, never lowered.
        A sequence behind the highest existing child suffix is safe (collision-skip covers
        it) but is still reported, because it means manual codes overtook the counter."""
        anomalies = []
        children = {}
        for a in rows:
            p = a.get("parent")
            if p:
                children.setdefault(p, []).append(a["code"])
        for a in rows:
            seq = a.get("next_child_seq")
            if seq is None:
                continue
            try:
                seq = int(seq)
            except (TypeError, ValueError):
                anomalies.append(f"{a['code']}: next_child_seq is not a number ({seq!r})")
                continue
            if not a.get("is_group") and seq > 0:
                anomalies.append(f"{a['code']}: non-group account holds next_child_seq={seq}")
                continue
            cap = SEQUENCE_CAP.get(len(a["code"]))
            if cap is not None and seq > cap:
                anomalies.append(f"{a['code']}: next_child_seq={seq} exceeds ceiling {cap}")
            kids = children.get(a["code"], [])
            if not kids or cap is None:
                continue
            try:
                pad = sequence_pad(a["code"])
                highest = max(int(k[len(a["code"]):]) for k in kids
                              if len(k) == len(a["code"]) + pad
                              and k[len(a["code"]):].isdigit())
            except (ValueError, KeyError):
                continue
            if seq < highest:
                anomalies.append(
                    f"{a['code']}: next_child_seq={seq} is behind the highest child "
                    f"suffix {highest} (manual codes overtook the counter)")
        return anomalies

    @staticmethod
    def _classify(*, rows, stamped_version, template_version, template_identical,
                  inconsistent, needs_review, has_custom) -> str:
        """PORT + ADAPT — Rahaal returned three states (`already_current`,
        `structure_mismatch`, `manual_review`). Same decision tree, expanded to the seven
        explicit states, and NO state ever triggers an automatic action.

          empty                 → the entity holds no accounts at all (seeding is allowed)
          inconsistent          → a structural defect exists (duplicate/cycle/orphan/bad
                                  prefix/level/origin/role/etc.) — human decision required
          manual_review         → the tree diverges from the template (missing, unexpected,
                                  wrong parent/type/group) — never auto-corrected
          older_version         → structure matches but an OLDER template version is stamped
                                  (no upgrade migration exists in this phase)
          structurally_matching → structure matches the template but no version is stamped
          custom_extended       → matches the current template PLUS user CUSTOM accounts
          already_current       → matches the current template exactly, stamp is current
        """
        if not rows:
            return "empty"
        if inconsistent:
            return "inconsistent"
        if needs_review or not template_identical:
            return "manual_review"
        if stamped_version is None:
            return "structurally_matching"
        try:
            stamped = int(stamped_version)
        except (TypeError, ValueError):
            return "manual_review"
        if stamped < int(template_version):
            return "older_version"
        if stamped > int(template_version):
            return "manual_review"        # newer than this build knows about
        if has_custom:
            return "custom_extended"
        return "already_current"
