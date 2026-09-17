"""ACCOUNT-LEVEL SCOPE — an extension of the existing Meraaj RBAC, not a second engine.

Permission answers «can this user reach the feature?». Scope answers «which accounts may
they see/use inside it?». Scope is stored on the SAME `db.user_roles` document that already
carries roles / extra_permissions / denied_permissions, and it is enforced in the BACKEND:
supplying an account id or code manually can never widen it.
"""
from typing import List, Optional

from fastapi import Depends, HTTPException

from db import db
from security import get_current_user

MODE_ALL = "all_accounts"
MODE_SELECTED = "selected_accounts"
MODE_SUBTREE = "account_subtree"
MODES = (MODE_ALL, MODE_SELECTED, MODE_SUBTREE)
MODE_LABELS = {MODE_ALL: "كل الحسابات المسموح بها",
               MODE_SELECTED: "حسابات محددة",
               MODE_SUBTREE: "شجرة حساب (حساب وفروعه)"}


class AccountScope:
    """`codes` are account CODES (stable, human-visible); empty + selected/subtree = deny."""

    def __init__(self, mode: str = MODE_ALL, codes: Optional[List[str]] = None):
        self.mode = mode if mode in MODES else MODE_ALL
        self.codes = [str(c).strip() for c in (codes or []) if str(c).strip()]

    @property
    def unrestricted(self) -> bool:
        return self.mode == MODE_ALL

    def public(self) -> dict:
        return {"mode": self.mode, "label_ar": MODE_LABELS[self.mode],
                "codes": self.codes, "unrestricted": self.unrestricted}

    def allowed_codes(self, accounts: List[dict]) -> set:
        """Resolve the scope against the real chart (parent chain, never a code prefix)."""
        if self.unrestricted:
            return {a["code"] for a in accounts}
        by_code = {a["code"]: a for a in accounts}
        if self.mode == MODE_SELECTED:
            return {c for c in self.codes if c in by_code}
        allowed = set()
        for acc in accounts:
            node, guard = acc, 0
            while node and guard < 64:
                if node["code"] in self.codes:
                    allowed.add(acc["code"])
                    break
                node = by_code.get(node.get("parent"))
                guard += 1
        return allowed

    def filter_accounts(self, accounts: List[dict]) -> List[dict]:
        allowed = self.allowed_codes(accounts)
        return [a for a in accounts if a["code"] in allowed]

    def filter_tree(self, roots: List[dict]) -> List[dict]:
        """Keep a node when it, or any descendant, is allowed — so the path stays visible."""
        def walk(node):
            kids = [w for w in (walk(c) for c in (node.get("children") or [])) if w]
            if node["code"] in self._allowed or kids:
                return {**node, "children": kids,
                        "out_of_scope": node["code"] not in self._allowed}
            return None
        return [w for w in (walk(r) for r in roots) if w]


async def load_scope(user: dict) -> AccountScope:
    if user.get("role") == "super_admin":
        return AccountScope(MODE_ALL)
    acting = user.get("_acting_staff")
    lookup_id = acting["id"] if acting else str(user["_id"])
    doc = await db.user_roles.find_one({"user_id": lookup_id}, {"account_scope": 1})
    sc = (doc or {}).get("account_scope") or {}
    return AccountScope(sc.get("mode", MODE_ALL), sc.get("codes"))


def account_scope():
    async def dep(user: dict = Depends(get_current_user)) -> AccountScope:
        return await load_scope(user)
    return dep


async def assert_accounts_allowed(scope: AccountScope, entity_id: str,
                                  codes: List[str]) -> None:
    """FAIL BEFORE the financial effect: a manually supplied code cannot bypass scope."""
    if scope.unrestricted or not codes:
        return
    from .adapters import chart
    accounts = await chart().list_accounts(entity_id, True)
    allowed = scope.allowed_codes(accounts)
    outside = sorted({str(c) for c in codes} - allowed)
    if outside:
        raise HTTPException(
            403, f"حسابات خارج نطاقك المحاسبي: {', '.join(outside)}")


async def scoped_accounts(scope: AccountScope, entity_id: str,
                          include_inactive: bool = True) -> List[dict]:
    from .adapters import chart
    return scope.filter_accounts(await chart().list_accounts(entity_id, include_inactive))


async def scoped_tree(scope: AccountScope, entity_id: str,
                      include_inactive: bool = True) -> List[dict]:
    from .adapters import chart
    roots = await chart().build_tree(entity_id, include_inactive)
    if scope.unrestricted:
        return roots
    scope._allowed = scope.allowed_codes(
        await chart().list_accounts(entity_id, include_inactive))
    return scope.filter_tree(roots)
