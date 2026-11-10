import { api } from "../api.js";
import { h, mount, statusChip, fmtDate, STATUS_LABEL, STATUS_ORDER, PRIORITY_LABEL } from "../util.js";

export async function tasksView(host, { args }) {
  const [tasks, projects] = await Promise.all([api("/tasks"), api("/projects")]);
  const pname = Object.fromEntries(projects.map((p) => [p.id, p.name]));
  const today = new Date().toISOString().slice(0, 10);
  let filter = args[0] || "ALL";
  const FILTERS = ["ALL", "overdue", ...STATUS_ORDER];
  const label = (f) => (f === "ALL" ? "Tất cả" : f === "overdue" ? "Quá hạn" : STATUS_LABEL[f]);
  const match = (t) => filter === "ALL" ? true
    : filter === "overdue" ? !["DONE", "CANCELLED"].includes(t.status_normalized) && t.due_date && t.due_date < today
    : t.status_normalized === filter;

  const tabs = h("div", { class: "tabs" });
  const body = h("div", { class: "card tablewrap" });
  function draw() {
    const rows = tasks.filter(match);
    mount(tabs, FILTERS.map((f) => h("button", { class: f === filter ? "on" : "", onclick: () => { filter = f; draw(); } }, `${label(f)} (${tasks.filter((t) => { const old = filter; filter = f; const r = match(t); filter = old; return r; }).length})`)));
    mount(body, rows.length ? h("table", {},
      h("thead", {}, h("tr", {}, ["Công việc", "Dự án", "Người phụ trách", "Trạng thái", "Ưu tiên", "Tiến độ", "Hạn"].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.map((t) => h("tr", {},
        h("td", {}, t.title), h("td", {}, pname[t.project_id] || "—"),
        h("td", {}, t.assignee_name_raw || (t.assignee_id ? "(đã liên kết)" : "—")),
        h("td", {}, statusChip(t.status_normalized)), h("td", {}, PRIORITY_LABEL[t.priority_normalized] || "—"),
        h("td", {}, t.progress === null ? "—" : [h("progress", { max: 100, value: t.progress }), " ", `${t.progress}%`]),
        h("td", {}, fmtDate(t.due_date)))))) : h("div", { class: "empty" }, "Không có công việc phù hợp."));
  }
  mount(host, h("h1", {}, "Công việc"), tabs, body);
  draw();
}
