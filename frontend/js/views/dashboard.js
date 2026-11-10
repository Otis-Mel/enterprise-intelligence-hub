import { api } from "../api.js";
import { h, mount, statusChip, fmtDate, pct, STATUS_LABEL, STATUS_ORDER } from "../util.js";

function kpi(label, value, tone = "") {
  return h("div", { class: "kpi " + tone }, h("div", { class: "v" }, value), h("div", { class: "l" }, label));
}

function attention(s) {
  const items = [];
  const add = (n, text, tone, href) => { if (n > 0) items.push(h("li", { class: tone }, href ? h("a", { href }, h("span", { class: "n" }, n), " ", text) : [h("span", { class: "n" }, n), " ", text])); };
  add(s.overdue, "việc đang quá hạn", "bad", "#/tasks/overdue");
  add(s.blocked, "việc đang bị chặn", "bad", "#/tasks/BLOCKED");
  add(s.pending_review, "bản ghi nhập đang chờ duyệt", "warn", "#/imports");
  add(s.due_soon, "việc đến hạn trong 7 ngày tới", "info");
  add(s.unknown_status, "việc có trạng thái chưa rõ (cần xác nhận)", "warn", "#/tasks/UNKNOWN");
  add(s.missing_assignee, "việc chưa có người phụ trách", "warn");
  add(s.unlinked_assignee, "việc có tên người phụ trách chưa khớp tài khoản", "info");
  add(s.missing_due_date, "việc chưa có hạn", "info");
  add(s.stale, "việc đang làm nhưng không cập nhật quá 14 ngày", "warn");
  return items.length ? h("ul", { class: "attn" }, items) : h("p", { class: "muted" }, "Không có gì cần chú ý.");
}

function ribbon(s) {
  const total = s.total || 1;
  const segs = STATUS_ORDER.filter((k) => s.by_status[k]).map((k) => {
    const seg = h("div", { class: "seg " + k, title: `${STATUS_LABEL[k]}: ${s.by_status[k]}` });
    seg.style.flexGrow = String(s.by_status[k] / total);
    return seg;
  });
  const legend = STATUS_ORDER.filter((k) => s.by_status[k]).map((k) =>
    h("span", {}, h("i", { class: "dot seg " + k }), `${STATUS_LABEL[k]} ${s.by_status[k]}`));
  return h("div", {}, h("div", { class: "ribbon", role: "img", "aria-label": "Phân bố trạng thái" }, segs), h("div", { class: "legend" }, legend));
}

function taskTable(rows, empty) {
  if (!rows.length) return h("p", { class: "muted" }, empty);
  return h("div", { class: "tablewrap" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Công việc", "Dự án", "Người phụ trách", "Hạn", "Trễ"].map((t) => h("th", {}, t)))),
    h("tbody", {}, rows.map((t) => h("tr", {},
      h("td", {}, t.title), h("td", {}, t.project || "—"), h("td", {}, t.assignee || "—"),
      h("td", {}, fmtDate(t.due_date)), h("td", {}, t.days_overdue > 0 ? `${t.days_overdue} ngày` : "—"))))));
}

export async function dashboardView(host) {
  const s = await api("/dashboard/summary");
  if (!s.total && !s.pending_review) {
    return mount(host, h("h1", {}, "Tổng quan"), h("div", { class: "card empty" },
      "Chưa có công việc nào trong phạm vi của bạn. ", h("a", { href: "#/imports" }, "Nhập dữ liệu từ file"), " để bắt đầu."));
  }
  mount(host,
    h("div", { class: "row spread" }, h("h1", {}, "Tổng quan"), h("span", { class: "muted small" }, `Tính đến ${fmtDate(s.as_of)}`)),
    h("div", { class: "card" }, h("h3", {}, "Cần chú ý"), attention(s)),
    h("div", { class: "grid" },
      kpi("Tổng số việc", s.total), kpi("Đang thực hiện", s.active),
      kpi("Tỷ lệ hoàn thành", pct(s.completion_rate), "ok"),
      kpi("Tiến độ TB (việc đang làm)", pct(s.avg_progress_active)),
      kpi("Quá hạn", s.overdue, s.overdue ? "bad" : ""), kpi("Bị chặn", s.blocked, s.blocked ? "bad" : "")),
    h("div", { class: "card" }, h("h3", {}, "Phân bố trạng thái"), ribbon(s),
      h("p", { class: "muted small" }, "Tỷ lệ hoàn thành = Hoàn thành ÷ (Tổng − Đã hủy). Việc chưa rõ trạng thái không bị đoán mà được đếm riêng.")),
    h("div", { class: "card" }, h("h3", {}, "Theo dự án"),
      s.by_project.length ? h("div", { class: "tablewrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Dự án", "Số việc", "Hoàn thành", "Quá hạn", "Bị chặn", "Tỷ lệ"].map((t) => h("th", {}, t)))),
        h("tbody", {}, s.by_project.map((p) => h("tr", {}, h("td", {}, p.name), h("td", {}, p.total), h("td", {}, p.done),
          h("td", {}, p.overdue), h("td", {}, p.blocked),
          h("td", {}, p.completion_rate === null ? "—" : [h("progress", { max: 100, value: p.completion_rate }), " ", pct(p.completion_rate)])))))) : h("p", { class: "muted" }, "Chưa có dự án.")),
    h("div", { class: "card" }, h("h3", {}, "Quá hạn (trễ nhiều nhất)"), taskTable(s.overdue_tasks, "Không có việc quá hạn.")),
    h("div", { class: "card" }, h("h3", {}, "Sắp đến hạn"), taskTable(s.upcoming_tasks, "Không có việc đến hạn trong 7 ngày tới.")));
}
