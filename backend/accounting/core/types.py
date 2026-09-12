from enum import Enum

from .errors import AccountingError


class AccountType(str, Enum):
    """The five accounting account types. Generic — no project may extend this."""
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


class AccountOrigin(str, Enum):
    """Who owns the account structurally, and therefore how protected it is.

    SYSTEM   — engine account the accounting logic itself posts to (opening suspense,
               retained earnings, FX result). Never deletable, never deactivatable, and
               its type/parent/is_group can never change.
    STANDARD — part of the seeded chart template. Never deletable; structure is locked.
    CUSTOM   — created by a user at runtime. Editable/deletable under the usage guards.
    """
    SYSTEM = "system"
    STANDARD = "standard"
    CUSTOM = "custom"


PROTECTED_ORIGINS = (AccountOrigin.SYSTEM, AccountOrigin.STANDARD)

# ---------------------------------------------------------------------------------------
# Hierarchical coding scheme (kept identical to the reference system studied in the
# architecture memo): the LEVEL of an account is a pure function of its code LENGTH, and a
# child's code always starts with its parent's code.
#   L1 = 1 digit   (root, e.g. "1")
#   L2 = 2 digits  (e.g. "11")
#   L3 = 4 digits  (e.g. "1101")
#   L4 = 7 digits  (terminal — an L4 account can never become a parent)
# ---------------------------------------------------------------------------------------
LEVEL_BY_CODE_LENGTH = {1: 1, 2: 2, 4: 3, 7: 4}
CHILD_CODE_LENGTH = {1: 2, 2: 4, 4: 7}
SEQUENCE_PAD = {1: 1, 2: 2, 4: 3}
SEQUENCE_CAP = {1: 9, 2: 99, 4: 999}
ROOT_CODE_LENGTH = 1
MAX_LEVEL = 4


def level_of_code(code: str) -> int:
    level = LEVEL_BY_CODE_LENGTH.get(len(code))
    if level is None:
        raise AccountingError(
            "coa.invalid_code_length",
            f"طول رمز الحساب غير صالح ({len(code)}) — الأطوال المسموحة: 1، 2، 4، 7 خانات",
        )
    return level


def child_code_length(parent_code: str) -> int:
    length = CHILD_CODE_LENGTH.get(len(parent_code))
    if length is None:
        raise AccountingError(
            "coa.terminal_account",
            f"الحساب {parent_code} حساب تحليلي نهائي (المستوى 4) — لا يمكن إنشاء حسابات تحته",
        )
    return length


def sequence_pad(parent_code: str) -> int:
    return SEQUENCE_PAD[len(parent_code)]


def sequence_cap(parent_code: str) -> int:
    return SEQUENCE_CAP[len(parent_code)]
