import { api, getToken, setToken } from "./api.js";
import { h, mount } from "./util.js";
import { loginView } from "./views/login.js";
import { dashboardView } from "./views/dashboard.js";
import { tasksView } from "./views/tasks.js";
import { importsView } from "./views/imports.js";
import { reviewView } from "./views/review.js";
import { reportsView } from "./views/reports.js";

const root = document.getElementById("root");
let me = null;

const ROUTES = {
  dashboard: { label: "Tổng quan", view: dashboardView },
  tasks: { label: "Công việc", view: tasksView },
  imports: { label: "Nhập dữ liệu", view: importsView },
  reports: { label: "Báo cáo", view: reportsView },
  review: { view: reviewView, hidden: true },
};

function parseHash() {
  const [name = "dashboard", ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  return { name: ROUTES[name] ? name : "dashboard", args: rest.map(decodeURIComponent) };
}

function logout() { setToken(null); me = null; render(); }

async function render() {
  if (!getToken()) return mount(root, loginView(async () => { await boot(); }));
  if (!me) {
    try { me = await api("/auth/me"); } catch { return mount(root, loginView(boot)); }
  }
  const { name, args } = parseHash();
  const main = h("main", {});
  const nav = h("nav", { class: "nav" },
    Object.entries(ROUTES).filter(([, r]) => !r.hidden).map(([k, r]) =>
      h("a", { href: "#/" + k, class: (k === name || (name === "review" && k === "imports")) ? "active" : "" }, r.label)));
  mount(root,
    h("header", { class: "topbar" },
      h("span", { class: "brand" }, "Enterprise Intelligence Hub"), nav,
      h("span", { class: "who" }, `${me.full_name} · ${me.role}`),
      h("button", { class: "btn", onclick: logout }, "Đăng xuất")),
    main);
  try { await ROUTES[name].view(main, { me, args }); }
  catch (e) { main.append(h("div", { class: "msg bad", role: "alert" }, e.message || String(e))); }
}

async function boot() { me = null; await render(); }

window.addEventListener("hashchange", render);
window.addEventListener("eih:logout", () => { me = null; render(); });
boot();
