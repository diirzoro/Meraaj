"""Business-side entry point for accounting effects (P1 flows).

Business modules call ONE function from here. They keep their own balance logic untouched:
this module never reads or writes a wallet, and never changes a business status.

TRACEABILITY
  emit_*()          ← Rahaal journal code inlined in each business route   ADAPT (one seam)
  balance mutation  ← Rahaal `updateBalance` in the same helper            LEAVE (business owns it)
"""
from typing import Optional

from .adapters import accounting_bridge
from .integration.account_links import LinkKey


def actor_from_user(user: Optional[dict], kind: str = "human") -> dict:
    """STABLE identity from the authenticated context only — never a name sent by the
    client. A `None` user means an automated action, which is labelled as such instead of
    being attributed to a fake human."""
    if not user:
        return {"id": "system", "label": "System / Automated", "kind": "system"}
    return {"id": str(user.get("_id") or user.get("id") or ""),
            "label": (user.get("name") or user.get("office_name")
                      or user.get("email") or "unknown"),
            "kind": kind}


async def emit_wallet_topup(topup: dict, topup_id: str, office: Optional[dict],
                            admin: Optional[dict]) -> dict:
    """Money received into the platform → the office's wallet claim grows.
    DEBIT cash/bank (asset ↑) · CREDIT wallet liability (obligation to the office ↑).
    A topup is NEVER revenue."""
    amount = topup["amount"]
    return await accounting_bridge().post_event(
        "wallet_topup", event_id=topup_id, currency=topup.get("currency", "USD"),
        amount=amount,
        lines=[(LinkKey.CASH, "debit", amount),
               (LinkKey.OFFICE_WALLET_LIABILITY, "credit", amount)],
        business_actor=actor_from_user(office),
        accounting_actor=actor_from_user(admin),
        description=f"شحن محفظة مكتب {topup.get('office_name', '')} "
                    f"({topup.get('method', '')})",
        business_ref={"office_id": topup.get("office_id"),
                      "method": topup.get("method")})


async def emit_wallet_withdrawal(withdrawal: dict, withdrawal_id: str,
                                 office: Optional[dict],
                                 admin: Optional[dict]) -> dict:
    """Money paid out of the platform → the office's wallet claim shrinks.
    DEBIT wallet liability (obligation ↓) · CREDIT cash/bank (asset ↓). Not an expense."""
    amount = withdrawal["amount"]
    return await accounting_bridge().post_event(
        "wallet_withdrawal", event_id=withdrawal_id,
        currency=withdrawal.get("currency", "USD"), amount=amount,
        lines=[(LinkKey.OFFICE_WALLET_LIABILITY, "debit", amount),
               (LinkKey.CASH, "credit", amount)],
        business_actor=actor_from_user(office),
        accounting_actor=actor_from_user(admin),
        description=f"سحب أرباح مكتب {withdrawal.get('office_name', '')} "
                    f"({withdrawal.get('method', '')})",
        business_ref={"office_id": withdrawal.get("office_id"),
                      "method": withdrawal.get("method")})


async def emit_b2b_transfer(transfer: dict, transfer_id: str,
                            sender: Optional[dict],
                            admin: Optional[dict]) -> dict:
    """Office → Office: a LIABILITY TRANSFER between two holders of the same obligation.
    It is NOT revenue and NOT expense: the platform's total obligation is unchanged, so the
    journal debits and credits the same liability account and carries both parties in its
    metadata (the per-office view lives in the Office Statement, not in the ledger)."""
    amount = transfer["amount"]
    return await accounting_bridge().post_event(
        "b2b_transfer", event_id=transfer_id,
        currency=transfer.get("currency", "USD"), amount=amount,
        lines=[(LinkKey.OFFICE_WALLET_LIABILITY, "debit", amount),
               (LinkKey.OFFICE_WALLET_LIABILITY, "credit", amount)],
        business_actor=actor_from_user(sender),
        accounting_actor=actor_from_user(admin),
        description=f"تحويل بين مكتبين: {transfer.get('from_office_name', '')} → "
                    f"{transfer.get('to_office_name', '')}",
        business_ref={"from_office_id": transfer.get("from_office_id"),
                      "to_office_id": transfer.get("to_office_id")})
