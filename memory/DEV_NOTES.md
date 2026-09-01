# Meraaj — Official Development Notes

## [P1 backlog] Office entity vs User — Owner + Staff/Sub-users model
Logged: 2026-09-01

### Current limitation (as-is)
Meraaj does NOT currently support an "Office Owner + Staff/Sub-users inside the SAME office
with a shared wallet and shared bookings". In the current data model:
- An "office" IS a single user account (`role="office"`).
- Wallet, transactions, topups, bookings, packages and ledger are ALL keyed by the
  account's own `_id` (office_id == _id), NOT by any office_ref/office_name.
- The only per-account permission mechanism is `rahal_permissions`
  (`{manage_packages, manage_bookings, approve_reject, can_refund, manage_settings}`),
  enforced by `require_permission` only for Rahal-linked offices.
- `rahal_office_ref` is only a label; sharing it across accounts does NOT merge wallets
  or bookings. There is no staff/sub-user concept.

### Required future design (do NOT implement in current batch)
Introduce a first-class Office entity, decoupled from User:
- **Office** entity independent of User (own `office_id`).
- **Office Owner** (manager) user.
- **Staff / Sub-users** users.
- All users linked to a single `office_id`.
- **One wallet per office** (not per user).
- **Bookings, Packages, Ledger, Escrow bound to the office**, not to the individual user.
- **Per-staff permissions** (granular, per user within the office).

### Note
Do NOT use `POST /api/integrations/rahal/offices/link` to fake a shared office — it will
NOT actually unify the wallet or bookings (they stay bound to each account's `_id`).
