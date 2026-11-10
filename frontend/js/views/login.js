import { login } from "../api.js";
import { h } from "../util.js";

export function loginView(onDone) {
  const msg = h("div", {});
  const email = h("input", { type: "email", required: true, autocomplete: "username", placeholder: "email@congty.com" });
  const pw = h("input", { type: "password", required: true, autocomplete: "current-password", placeholder: "Mật khẩu" });
  const btn = h("button", { class: "btn primary", type: "submit" }, "Đăng nhập");
  const form = h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault();
    btn.disabled = true; msg.textContent = "";
    try { await login(email.value.trim(), pw.value); await onDone(); }
    catch (err) { msg.replaceChildren(h("div", { class: "msg bad", role: "alert" }, err.status === 401 ? "Sai email hoặc mật khẩu." : err.message)); btn.disabled = false; }
  } }, h("h1", {}, "Enterprise Intelligence Hub"), h("p", { class: "muted small" }, "Đăng nhập để xem tiến độ và duyệt dữ liệu nhập."), email, pw, msg, btn);
  return h("div", { class: "login" }, form);
}
