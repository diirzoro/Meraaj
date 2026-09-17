"""Chart-of-Accounts templates — DATA ONLY (no engine logic, no business logic).

PORT — Rahaal `lib/coa.js`:
  • `COA_TEMPLATE`          → STANDARD_COA (structure, codes, types, parents, is_group)
  • `CURRENT_COA_VERSION=2` → STANDARD_COA_VERSION = 2 (kept at 2 so the lineage with the
                              reference implementation stays provable)
  • `C` (canonical codes)   → the same codes, now reachable through semantic ROLES

LEAVE (travel-activity accounts, deliberately NOT part of the generic core template):
  • 4101 إيرادات عمولات التذاكر   (tickets)
  • 4102 إيرادات عمولات التأشيرات (visas)
  • 53   فروق العمولات            (travel partner commission differences)
  They are preserved verbatim in RAHAAL_TRAVEL_EXTRAS purely for traceability/parity, and
  are never seeded by Meraaj.

HARDEN vs Rahaal:
  • Rahaal marked ONLY 3103 as `is_system`; every other template account could be deleted
    by a user (including 3102 Retained Earnings, whose loss breaks year-closing). Here the
    whole template is protected: engine accounts are SYSTEM, the rest are STANDARD, and
    neither is deletable.
  • Rahaal had `name_ar` only → `name` (EN) + `name_ar` (AR) so the module is portable.
  • Numbering gaps left by dropped travel leaves are NOT re-used, so any historical
    Rahaal code keeps its original meaning.
"""
from ..core.roles import (
    ASSETS, CURRENT_ASSETS, NON_CURRENT_ASSETS, CASH_ON_HAND, BANKS_AND_WALLETS,
    RECEIVABLES, LIABILITIES, CURRENT_LIABILITIES, PAYABLES, LONG_TERM_LIABILITIES,
    EQUITY, EQUITY_GROUP, CAPITAL, RETAINED_EARNINGS, OPENING_BALANCE_SUSPENSE,
    REVENUES, OPERATING_REVENUE_GROUP, SERVICE_REVENUE, FX_RESULT,
    CANCELLATION_FEE_REVENUE, EXPENSES, OPERATING_EXPENSE_GROUP, OPERATING_EXPENSES,
    ADMIN_EXPENSE_GROUP, FX_ADJUSTMENT,
)
from ..core.template import ChartTemplate, TemplateAccount as T
from ..core.types import AccountType as AT, AccountOrigin as AO

STANDARD_COA_VERSION = 2

# Canonical codes — PORT of Rahaal's `C` map (same numbers, same meaning).
CODES = {
    ASSETS: "1", CURRENT_ASSETS: "11", CASH_ON_HAND: "1101",
    BANKS_AND_WALLETS: "1102", RECEIVABLES: "1103", NON_CURRENT_ASSETS: "12",
    LIABILITIES: "2", CURRENT_LIABILITIES: "21", PAYABLES: "2101",
    LONG_TERM_LIABILITIES: "22",
    EQUITY: "3", EQUITY_GROUP: "31", CAPITAL: "3101", RETAINED_EARNINGS: "3102",
    OPENING_BALANCE_SUSPENSE: "3103",
    REVENUES: "4", OPERATING_REVENUE_GROUP: "41", SERVICE_REVENUE: "4103",
    FX_RESULT: "4104", CANCELLATION_FEE_REVENUE: "4105",
    EXPENSES: "5", OPERATING_EXPENSE_GROUP: "51", ADMIN_EXPENSE_GROUP: "52",
    OPERATING_EXPENSES: "5101", FX_ADJUSTMENT: "5201",
}
C = CODES

_ROWS = [
    # ---------------------------------------------------------------- 1 ASSETS
    T(C[ASSETS], "Assets", "الأصول", AT.ASSET, None, True, AO.STANDARD, ASSETS),
    T(C[CURRENT_ASSETS], "Current assets", "الأصول المتداولة", AT.ASSET,
      C[ASSETS], True, AO.STANDARD, CURRENT_ASSETS),
    T(C[CASH_ON_HAND], "Cash on hand", "الصناديق", AT.ASSET,
      C[CURRENT_ASSETS], True, AO.STANDARD, CASH_ON_HAND, accepts_children=True),
    T(C[BANKS_AND_WALLETS], "Banks and wallets", "البنوك والمحافظ", AT.ASSET,
      C[CURRENT_ASSETS], True, AO.STANDARD, BANKS_AND_WALLETS, accepts_children=True),
    T(C[RECEIVABLES], "Receivables", "المدينون / ذمم مدينة", AT.ASSET,
      C[CURRENT_ASSETS], True, AO.STANDARD, RECEIVABLES, accepts_children=True),
    T(C[NON_CURRENT_ASSETS], "Non-current assets", "الأصول الثابتة / غير المتداولة",
      AT.ASSET, C[ASSETS], True, AO.STANDARD, NON_CURRENT_ASSETS),
    # ---------------------------------------------------------- 2 LIABILITIES
    T(C[LIABILITIES], "Liabilities", "الخصوم / الالتزامات", AT.LIABILITY, None, True,
      AO.STANDARD, LIABILITIES),
    T(C[CURRENT_LIABILITIES], "Current liabilities", "الالتزامات المتداولة",
      AT.LIABILITY, C[LIABILITIES], True, AO.STANDARD, CURRENT_LIABILITIES),
    T(C[PAYABLES], "Payables", "الدائنون / ذمم دائنة", AT.LIABILITY,
      C[CURRENT_LIABILITIES], True, AO.STANDARD, PAYABLES, accepts_children=True),
    T(C[LONG_TERM_LIABILITIES], "Long-term liabilities",
      "الالتزامات طويلة الأجل / غير المتداولة", AT.LIABILITY, C[LIABILITIES], True,
      AO.STANDARD, LONG_TERM_LIABILITIES),
    # --------------------------------------------------------------- 3 EQUITY
    T(C[EQUITY], "Equity", "حقوق الملكية", AT.EQUITY, None, True, AO.STANDARD, EQUITY),
    T(C[EQUITY_GROUP], "Capital and equity", "رأس المال وحقوق الملكية", AT.EQUITY,
      C[EQUITY], True, AO.STANDARD, EQUITY_GROUP),
    T(C[CAPITAL], "Capital", "رأس المال", AT.EQUITY, C[EQUITY_GROUP], False,
      AO.STANDARD, CAPITAL),
    # HARDEN — SYSTEM (Rahaal left 3102 unprotected; losing it breaks year-closing).
    T(C[RETAINED_EARNINGS], "Retained earnings", "الأرباح المبقاة", AT.EQUITY,
      C[EQUITY_GROUP], False, AO.SYSTEM, RETAINED_EARNINGS),
    # PORT — Rahaal's only is_system account.
    T(C[OPENING_BALANCE_SUSPENSE], "Opening balance suspense",
      "تسوية الأرصدة الافتتاحية", AT.EQUITY, C[EQUITY_GROUP], False, AO.SYSTEM,
      OPENING_BALANCE_SUSPENSE),
    # -------------------------------------------------------------- 4 REVENUE
    T(C[REVENUES], "Revenues", "الإيرادات", AT.REVENUE, None, True, AO.STANDARD, REVENUES),
    T(C[OPERATING_REVENUE_GROUP], "Operating revenue", "إيرادات النشاط", AT.REVENUE,
      C[REVENUES], True, AO.STANDARD, OPERATING_REVENUE_GROUP),
    T(C[SERVICE_REVENUE], "Service revenue", "إيرادات خدمات", AT.REVENUE,
      C[OPERATING_REVENUE_GROUP], False, AO.STANDARD, SERVICE_REVENUE),
    # HARDEN — SYSTEM: the currency engine posts here automatically in a later phase.
    T(C[FX_RESULT], "FX gains and losses", "أرباح وخسائر فروق العملات", AT.REVENUE,
      C[OPERATING_REVENUE_GROUP], False, AO.SYSTEM, FX_RESULT),
    T(C[CANCELLATION_FEE_REVENUE], "Cancellation and refund fees", "رسوم إلغاء واسترداد",
      AT.REVENUE, C[OPERATING_REVENUE_GROUP], False, AO.STANDARD,
      CANCELLATION_FEE_REVENUE),
    # -------------------------------------------------------------- 5 EXPENSE
    T(C[EXPENSES], "Expenses", "المصروفات", AT.EXPENSE, None, True, AO.STANDARD, EXPENSES),
    T(C[OPERATING_EXPENSE_GROUP], "Operating expenses", "مصاريف تشغيلية", AT.EXPENSE,
      C[EXPENSES], True, AO.STANDARD, OPERATING_EXPENSE_GROUP),
    T(C[ADMIN_EXPENSE_GROUP], "Administrative and general expenses",
      "مصاريف إدارية وعمومية", AT.EXPENSE, C[EXPENSES], True, AO.STANDARD,
      ADMIN_EXPENSE_GROUP),
    T(C[OPERATING_EXPENSES], "Operating expenses (detail)", "مصاريف تشغيلية (تفصيلي)",
      AT.EXPENSE, C[OPERATING_EXPENSE_GROUP], True, AO.STANDARD, OPERATING_EXPENSES,
      accepts_children=True),
    # HARDEN — SYSTEM: currency-difference adjustments post here in a later phase.
    T(C[FX_ADJUSTMENT], "FX differences and adjustments", "فروق عملة وتسويات",
      AT.EXPENSE, C[ADMIN_EXPENSE_GROUP], False, AO.SYSTEM, FX_ADJUSTMENT),
]

STANDARD_COA = ChartTemplate(
    key="standard_v2",
    title="دليل حسابات قياسي (مستخرج من Rahaal COA v2)",
    version=STANDARD_COA_VERSION,
    accounts=_ROWS,
)

# LEAVE — kept for traceability only; never seeded into a Meraaj entity.
RAHAAL_TRAVEL_EXTRAS = [
    T("4101", "Ticket commission revenue", "إيرادات عمولات التذاكر", AT.REVENUE,
      "41", False, AO.STANDARD, "travel_ticket_revenue"),
    T("4102", "Visa commission revenue", "إيرادات عمولات التأشيرات والموافقات",
      AT.REVENUE, "41", False, AO.STANDARD, "travel_visa_revenue"),
    T("53", "Commission differences", "فروق العمولات", AT.EXPENSE, "5", True,
      AO.STANDARD, "travel_commission_diff"),
]
