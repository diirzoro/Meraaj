/** MOBILE API LAYER — the single place the app talks to Meraaj.
 *
 *  Screens never import axios directly: changing a base path or adding an API version
 *  happens here only. Everything money- or booking-related is decided by the server;
 *  the app only displays what the server returns.
 */
import api, { apiError } from "@/lib/api";

export const MOBILE_API = "/v1/mobile";
export const APP_VERSION = "1.0.0";

export { apiError };

/** Retries GETs on transport errors only — never a write (no duplicate bookings/top-ups). */
async function safeGet(path, { retries = 2, params } = {}) {
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const r = await api.get(path, { params });
      return r.data;
    } catch (e) {
      const status = e?.response?.status;
      lastError = e;
      if (status && status !== 502 && status !== 503 && status !== 504) throw e;
      await new Promise((res) => setTimeout(res, 400 * (attempt + 1)));
    }
  }
  throw lastError;
}

export const mobileApi = {
  // ---- shell (server-driven: tabs, services, flags, version gate)
  config: () => safeGet(`${MOBILE_API}/config`),
  bootstrap: () => safeGet(`${MOBILE_API}/bootstrap`),
  home: () => safeGet(`${MOBILE_API}/home`),
  ticketProviders: () => safeGet(`${MOBILE_API}/tickets/providers`),

  // ---- reused Meraaj endpoints (no mobile-specific business logic)
  programs: (params) => safeGet("/packages", { params }),
  program: (id) => safeGet(`/packages/${id}`),
  bookings: (role = "buyer") => safeGet("/bookings", { params: { role } }),
  booking: (id) => safeGet(`/bookings/${id}`),
  bookingTimeline: (id) => safeGet(`/bookings/${id}/timeline`),
  wallet: () => safeGet("/wallet"),
  transactions: () => safeGet("/wallet/transactions"),
  topups: () => safeGet("/wallet/topups"),
  withdrawals: () => safeGet("/wallet/withdrawals"),
  notifications: () => safeGet("/notifications"),
  officeStatement: (params) => safeGet("/office-statement", { params }),

  // ---- writes: single attempt, server validates price/balance/commission
  createBooking: (payload) => api.post("/bookings", payload).then((r) => r.data),
  createTopup: (payload) => api.post("/wallet/topups", payload).then((r) => r.data),
  requestWithdrawal: (payload) => api.post("/wallet/withdrawals", payload).then((r) => r.data),
  markNotificationRead: (id) => api.post(`/notifications/${id}/read`).then((r) => r.data),
  markAllNotificationsRead: () => api.post("/notifications/read-all").then((r) => r.data),
};

export default mobileApi;
