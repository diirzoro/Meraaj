import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const api = axios.create({ baseURL: API, withCredentials: true });

const saved = localStorage.getItem("meraaj_token");
if (saved) api.defaults.headers.common["Authorization"] = `Bearer ${saved}`;

export const setToken = (t) => {
  if (t) {
    localStorage.setItem("meraaj_token", t);
    api.defaults.headers.common["Authorization"] = `Bearer ${t}`;
  } else {
    localStorage.removeItem("meraaj_token");
    delete api.defaults.headers.common["Authorization"];
  }
};

export function apiError(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return "حدث خطأ. حاول مرة أخرى.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  return String(d);
}

api.interceptors.response.use(
  (r) => r,
  (e) => {
    const status = e?.response?.status;
    const detail = e?.response?.data?.detail || "";
    if (status === 403 && typeof detail === "string" && detail.includes("موقوف")) {
      setToken(null);
      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login?suspended=1";
      }
    }
    return Promise.reject(e);
  }
);

export default api;
