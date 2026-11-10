// Mọi nội dung hiển thị đều đi qua textContent / createTextNode: dữ liệu import là không tin cậy, không bao giờ dùng innerHTML.
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, children);
  return el;
}
function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
export function mount(el, ...children) { clear(el); append(el, children); }

export const STATUS_LABEL = { TODO: "Chưa làm", IN_PROGRESS: "Đang làm", BLOCKED: "Bị chặn", DONE: "Hoàn thành", CANCELLED: "Đã hủy", UNKNOWN: "Chưa rõ" };
export const PRIORITY_LABEL = { LOW: "Thấp", MEDIUM: "Trung bình", HIGH: "Cao", CRITICAL: "Khẩn", UNKNOWN: "Chưa rõ" };
export const REVIEW_LABEL = { PENDING: "Cần xem", CLEAN: "Sạch", APPROVED: "Đã duyệt", REJECTED: "Từ chối", IMPORTED: "Đã nhập" };
export const FILE_STATUS_LABEL = {
  UPLOADED: "Đã tải lên", PARSING: "Đang đọc", NEEDS_MAPPING: "Chờ chuẩn hóa", NEEDS_REVIEW: "Cần duyệt",
  VALIDATED: "Đã kiểm tra", APPROVED: "Đã duyệt", IMPORTED: "Đã nhập", FAILED: "Lỗi",
};
export const STATUS_ORDER = ["TODO", "IN_PROGRESS", "BLOCKED", "DONE", "CANCELLED", "UNKNOWN"];

export function statusChip(s) {
  const cls = { DONE: "ok", BLOCKED: "bad", IN_PROGRESS: "info", UNKNOWN: "warn" }[s] || "";
  return h("span", { class: "chip " + cls }, STATUS_LABEL[s] || s);
}
export function reviewChip(s) {
  const cls = { APPROVED: "ok", IMPORTED: "ok", REJECTED: "bad", PENDING: "warn", CLEAN: "info" }[s] || "";
  return h("span", { class: "chip " + cls }, REVIEW_LABEL[s] || s);
}
export function fmtDate(d) {
  if (!d) return "—";
  const [y, m, day] = String(d).slice(0, 10).split("-");
  return y && m && day ? `${day}/${m}/${y}` : String(d);
}
export function pct(v) { return v === null || v === undefined ? "—" : `${Math.round(v * 10) / 10}%`; }
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export function showError(host, err) {
  host.prepend(h("div", { class: "msg bad", role: "alert" }, err && err.message ? err.message : String(err)));
}
