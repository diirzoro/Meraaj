"""Account-code generation and validation.

PORT — Rahaal `generateSubAccountCode()` + `accountCodeExists()` + the manual-code
validation block of `POST /accounts`. The algorithm is preserved step by step:

  1. level scheme derived from code length: L1=1, L2=2, L3=4, L4=7 digits
  2. pad/cap per parent length: {1: pad 1 cap 9}, {2: pad 2 cap 99}, {4: pad 3 cap 999}
  3. terminal-node protection: an L4 (7-digit) account can never have children
  4. atomic sequence reservation on the parent document ($inc next_child_seq)
  5. collision-skip loop: if the generated code is already taken (legacy/manual codes),
     reserve the NEXT sequence instead of failing, with a 500-iteration guard
  6. sequence-cap error telling the user to create a new group
  7. a child's code ALWAYS starts with its parent's code — by construction

ADAPT: JavaScript `String(seq).padStart(pad,'0')` → Python `str(seq).zfill(...)`;
`while (await accountCodeExists(...))` → the same loop with `await` in Python.
Nothing about the numbering behaviour changed.
"""
from typing import Optional, Tuple

from .errors import AccountingError
from .types import child_code_length, sequence_pad, sequence_cap, ROOT_CODE_LENGTH

MAX_COLLISION_GUARD = 500


def assert_parent_can_have_children(parent_code: str) -> None:
    """PORT — Rahaal terminal-node protection (`parentStr.length >= 7` → throw)."""
    if len(parent_code) >= 7:
        raise AccountingError(
            "coa.terminal_account",
            f"الحساب {parent_code} حساب تحليلي نهائي (المستوى 4) — لا يمكن إنشاء حسابات "
            f"فرعية تحته. القيود المحاسبية فقط تتم على هذا المستوى")
    if len(parent_code) not in (1, 2, 4):
        raise AccountingError(
            "coa.invalid_parent_code",
            f"رمز الحساب الأب غير صالح ({parent_code}) — الأطوال المسموحة: 1، 2، 4 خانات")


async def generate_sub_account_code(store, entity_id: str,
                                    parent_code: str) -> Tuple[str, int]:
    """PORT of Rahaal `generateSubAccountCode(db, tenantId, parentCode)`.

    Returns `(account_code, account_seq)`. Raises `AccountingError` with the same three
    failure modes Rahaal had: parent missing, sequence exhausted, generation impossible.
    """
    parent_code = str(parent_code)
    assert_parent_can_have_children(parent_code)
    pad = sequence_pad(parent_code)
    cap = sequence_cap(parent_code)

    seq = await store.bump_child_sequence(entity_id, parent_code)
    if seq is None:
        raise AccountingError("coa.parent_not_found",
                              f"الحساب الأب {parent_code} غير موجود في الدليل", 404)
    new_code = parent_code + str(seq).zfill(pad)

    guard = 0
    # PORT — collision-skip: legacy or manually created codes never break the generator.
    while await store.code_exists(entity_id, new_code):
        guard += 1
        if guard > MAX_COLLISION_GUARD:
            raise AccountingError("coa.code_generation_failed",
                                  "تعذر توليد رمز حساب — تواصل مع الدعم", 500)
        seq = await store.bump_child_sequence(entity_id, parent_code)
        if seq is None:
            raise AccountingError("coa.parent_not_found",
                                  f"الحساب الأب {parent_code} غير موجود في الدليل", 404)
        if seq > cap:
            raise AccountingError(
                "coa.sequence_exhausted",
                f"امتلأ تسلسل الفرع {parent_code} (الحد {cap} حساباً) — أنشئ مجموعة جديدة")
        new_code = parent_code + str(seq).zfill(pad)

    if seq > cap:
        raise AccountingError(
            "coa.sequence_exhausted",
            f"امتلأ تسلسل الفرع {parent_code} (الحد {cap} حساباً) — أنشئ مجموعة جديدة")
    return new_code, seq


async def preview_next_code(store, entity_id: str, parent_code: str) -> str:
    """PORT — Rahaal `GET /accounts/next-code`: a READ-ONLY preview that does NOT increment
    `next_child_seq`. Atomic allocation still happens only at creation time, so a preview
    can never cause a collision, a hole in the sequence, or a renumbering."""
    parent = await store.get_by_code(entity_id, parent_code)
    if not parent:
        raise AccountingError("coa.parent_not_found", "الحساب الأب غير موجود", 404)
    assert_parent_can_have_children(parent_code)
    if not parent.get("is_group"):
        raise AccountingError(
            "coa.parent_not_group",
            f"الحساب الأب {parent_code} ليس حساب مجموعة (Group) — لا يمكن إنشاء حسابات "
            f"فرعية إلا تحت حسابات المجموعات")
    pad = sequence_pad(parent_code)
    cap = sequence_cap(parent_code)
    seq = int(parent.get("next_child_seq") or 0) + 1
    code = parent_code + str(seq).zfill(pad)
    guard = 0
    while await store.code_exists(entity_id, code):
        guard += 1
        if guard > MAX_COLLISION_GUARD:
            raise AccountingError("coa.code_generation_failed",
                                  "تعذر توليد رمز حساب — تواصل مع الدعم", 500)
        seq += 1
        if seq > cap:
            raise AccountingError(
                "coa.sequence_exhausted",
                f"امتلأ تسلسل الفرع {parent_code} (الحد {cap} حساباً) — أنشئ مجموعة جديدة")
        code = parent_code + str(seq).zfill(pad)
    if seq > cap:
        raise AccountingError(
            "coa.sequence_exhausted",
            f"امتلأ تسلسل الفرع {parent_code} (الحد {cap} حساباً) — أنشئ مجموعة جديدة")
    return code


async def sync_parent_sequence_after_manual_code(store, entity_id: str,
                                                 parent_code: Optional[str],
                                                 code: str) -> Optional[int]:
    """HARDEN (limited ADAPT, Phase 2) — keep `next_child_seq` from falling behind a
    manually supplied code.

    Rahaal relied purely on the collision-skip loop: a manual `1101050` left the counter at
    0, so the next 50 automatic allocations each burned one wasted `$inc` round-trip before
    finding a free code. Behaviour was correct, cost was not.

    This raises the counter to the manual suffix ONLY WHEN IT IS BEHIND. It never lowers it,
    never renumbers anything, never touches existing documents other than the parent's
    counter, and the collision-skip loop plus the unique index both stay exactly as they
    were — so this is an optimisation of an invariant, not a replacement for it.
    """
    if not parent_code:
        return None
    suffix = code[len(parent_code):]
    if not suffix.isdigit():
        return None
    try:
        pad = sequence_pad(parent_code)
    except KeyError:
        return None
    if len(suffix) != pad:
        return None
    value = int(suffix)
    parent = await store.get_by_code(entity_id, parent_code)
    if not parent:
        return None
    current = int(parent.get("next_child_seq") or 0)
    if value <= current:
        return None
    await store.set_child_sequence(entity_id, parent_code, value)
    return value


def validate_manual_code(code: str, parent_code: Optional[str]) -> None:
    """PORT — Rahaal manual-code validation in `POST /accounts`, rule for rule:
      • digits only
      • must start with the parent's prefix
      • exact length for the level under that parent ({1:2, 2:4, 4:7})
      • a root account (no parent) has a 1-digit code only
    """
    if not code.isdigit():
        raise AccountingError("coa.code_not_numeric",
                              "رمز الحساب يجب أن يكون أرقاماً فقط")
    if parent_code:
        if not code.startswith(parent_code):
            raise AccountingError(
                "coa.code_prefix_violation",
                f"رمز الحساب يجب أن يبدأ ببادئة الأب ({parent_code}...) — "
                f"لا يجوز إنشاء {code} تحت {parent_code}")
        expected = child_code_length(parent_code)
        if len(code) != expected:
            filler = "0" * (expected - len(parent_code) - 1)
            raise AccountingError(
                "coa.code_length_violation",
                f"طول الرمز تحت الأب {parent_code} يجب أن يكون {expected} خانات "
                f"(مثال: {parent_code}{filler}1)")
    else:
        if len(code) != ROOT_CODE_LENGTH:
            raise AccountingError(
                "coa.root_code_length",
                "الحسابات الجذرية (بدون أب) رمزها خانة واحدة فقط (1-9)")
        if code == "0":
            raise AccountingError("coa.root_code_length",
                                  "رمز الحساب الجذري يجب أن يكون بين 1 و 9")
