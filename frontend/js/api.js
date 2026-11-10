const KEY = "eih_token";
let memToken = null;

export function getToken() {
  try { return sessionStorage.getItem(KEY) || memToken; } catch { return memToken; }
}
export function setToken(t) {
  memToken = t;
  try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch { /* bỏ qua: chế độ riêng tư */ }
}

export class ApiError extends Error {
  constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; }
}

function describe(detail, status) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  return `Lỗi ${status}`;
}

export async function api(path, { method = "GET", body, form, query } = {}) {
  const url = new URL("/api/v1" + path, window.location.origin);
  for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = "Bearer " + token;
  let payload;
  if (form instanceof FormData) payload = form;
  else if (form) { payload = new URLSearchParams(form); }
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, { method, headers, body: payload }); }
  catch { throw new ApiError(0, "Không kết nối được máy chủ."); }
  if (res.status === 401 && token) { setToken(null); window.dispatchEvent(new Event("eih:logout")); }
  let data = null;
  try { data = await res.json(); } catch { /* không có JSON */ }
  if (!res.ok) throw new ApiError(res.status, describe(data && data.detail, res.status), data && data.detail);
  return data;
}

export const login = async (email, password) => {
  const r = await api("/auth/login", { method: "POST", form: { username: email, password } });
  setToken(r.access_token);
};
