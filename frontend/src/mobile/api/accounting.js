/** Mobile accounting API surface — the SAME Batch 2 endpoints, no parallel engine.
 *  Every capability shown is decided by `bootstrap.accounting.capabilities` (backend RBAC),
 *  and every sensitive operation is re-authorised server-side. */
import api from "@/lib/api";

const ACC = "/accounting";

export const accApi = {
  accountsTree: () => api.get(`${ACC}/accounts/tree?include_inactive=true`).then((r) => r.data),
  accounts: () => api.get(`${ACC}/accounts?include_inactive=false`).then((r) => r.data),
  vouchers: (kind) => api.get(`${ACC}/vouchers?kind=${kind}`).then((r) => r.data),
  createVoucher: (payload, idem) => api.post(`${ACC}/vouchers`, payload,
    { headers: idem ? { "Idempotency-Key": idem } : {} }).then((r) => r.data),
  approveVoucher: (id) => api.post(`${ACC}/vouchers/${id}/approve`).then((r) => r.data),
  cancelVoucher: (id, reason) =>
    api.post(`${ACC}/vouchers/${id}/cancel?reason=${encodeURIComponent(reason)}`).then((r) => r.data),
  journals: () => api.get(`${ACC}/journal/entries?limit=50`).then((r) => r.data),
  journal: (id) => api.get(`${ACC}/journal/entries/${id}`).then((r) => r.data),
  reverseJournal: (id, reason) =>
    api.post(`${ACC}/journal/entries/${id}/reverse?reason=${encodeURIComponent(reason)}`).then((r) => r.data),
  ledger: (code, params) => api.get(`${ACC}/ledger/account/${encodeURIComponent(code)}`,
    { params }).then((r) => r.data),
  trialBalance: (currency) => api.get(`${ACC}/reports/trial-balance?currency=${currency}`).then((r) => r.data),
  incomeStatement: (currency) => api.get(`${ACC}/reports/income-statement?currency=${currency}`).then((r) => r.data),
  balanceSheet: (currency) => api.get(`${ACC}/reports/balance-sheet?currency=${currency}`).then((r) => r.data),
  periods: (year) => api.get(`${ACC}/periods?fiscal_year=${year}`).then((r) => r.data),
  yearStatus: (year) => api.get(`${ACC}/year-close/${year}`).then((r) => r.data),
  closePeriod: (id, reason) =>
    api.post(`${ACC}/periods/${id}/close?reason=${encodeURIComponent(reason)}`).then((r) => r.data),
  reopenPeriod: (id, reason) =>
    api.post(`${ACC}/periods/${id}/reopen?reason=${encodeURIComponent(reason)}`).then((r) => r.data),
  reconciliation: () => api.get(`${ACC}/integration/reconciliation?limit=200`).then((r) => r.data),
  selfAudit: () => api.get(`${ACC}/self-audit`).then((r) => r.data),
};

export default accApi;
