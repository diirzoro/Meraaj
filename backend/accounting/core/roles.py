"""Semantic account roles — the stable vocabulary later phases will use.

Business logic must ask for a ROLE ("the opening-balance suspense account") and never for
a number ("3103"). This is the single change that makes the chart renumberable and the
module portable to another project.
"""

# Structure
ASSETS = "assets"
CURRENT_ASSETS = "current_assets"
NON_CURRENT_ASSETS = "non_current_assets"
CASH_ON_HAND = "cash_on_hand"
BANKS_AND_WALLETS = "banks_and_wallets"
RECEIVABLES = "receivables"

LIABILITIES = "liabilities"
CURRENT_LIABILITIES = "current_liabilities"
PAYABLES = "payables"
LONG_TERM_LIABILITIES = "long_term_liabilities"

EQUITY = "equity"
EQUITY_GROUP = "equity_group"
CAPITAL = "capital"
RETAINED_EARNINGS = "retained_earnings"
OPENING_BALANCE_SUSPENSE = "opening_balance_suspense"

REVENUES = "revenues"
OPERATING_REVENUE_GROUP = "operating_revenue_group"
SERVICE_REVENUE = "service_revenue"
FX_RESULT = "fx_result"
#: Phase 10 vocabulary. The FX engine resolves FX_GAIN → FX_RESULT and FX_LOSS →
#: FX_ADJUSTMENT when a chart profile does not define the dedicated roles, so no account
#: NUMBER is ever hardcoded in the Core.
FX_GAIN = "fx_gain"
FX_LOSS = "fx_loss"
CANCELLATION_FEE_REVENUE = "cancellation_fee_revenue"

EXPENSES = "expenses"
OPERATING_EXPENSE_GROUP = "operating_expense_group"
OPERATING_EXPENSES = "operating_expenses"
ADMIN_EXPENSE_GROUP = "admin_expense_group"
FX_ADJUSTMENT = "fx_adjustment"

# Roles reserved for host-project chart profiles (declared here so the vocabulary stays in
# one place; the Core itself never references them).
CLIENT_WALLET_LIABILITY = "client_wallet_liability"
ADS_REVENUE = "ads_revenue"
PLATFORM_COMMISSION_REVENUE = "platform_commission_revenue"
REFUNDS_AND_REVERSALS = "refunds_and_reversals"
