import { api } from "../api.js";
import { h, mount, fmtDate, pct, STATUS_LABEL, STATUS_ORDER } from "../util.js";

const STATUS = { DRAFT: ["Bản nháp", "warn"], PUBLISHED: ["Chính thức", "ok"] };
const METHOD = { gemini: "Gemini diễn đạt (đã kiểm tra số liệu)", template: "Mẫu cố định (không dùng AI)" };

function section(title, items) {
  if (!items || !items.length) return null;
  return h("div", { class: "card" }, h("h3", {}, title), h("ul", { class: "plain" }, items.map((t) => h("li", {}, t))));
}

async function detail(host, me, id) {
  const r = await api(`/reports/${id}`);
  const k = r.kpis;
  const msg = h("div", {});
  const isLeader = me.role === "DEPT_LEADER";
  const canDelete = r.status === "DRAFT" && ["PM", "DEPT_LEADER"].includes(me.role);
  const [label, tone] = STATUS[r.status] || [r.status, ""];
  mount(host,
    h("p", {}, h("a", { href: "#/reports" }, "← Danh sách báo cáo")),
    h("div", { class: "row spread" }, h("h1", {}, r.title), h("span", { class: "chip " + tone }, label)),
    h("p", { class: "muted small" }, `Số liệu tính đến ${fmtDate(r.as_of)} · tạo lúc ${fmtDate(r.created_at)}`
      + (r.published_at ? ` · duyệt ${fmtDate(r.published_at)}` : "")),
    msg,
    h("div", { class: "card" }, h("h3", {}, "Tóm tắt"), h("p", {}, r.narrative.headline),
      h("p", { class: "muted small" }, "Cách viết nhận xét: " + (METHOD[r.narrative_method] || r.narrative_method))),
    r.narrative_notes.length ? h("div", { class: "msg info" }, "Bản Gemini bị loại và thay bằng mẫu cố định vì: " + r.narrative_notes.join("; ")) : null,
    section("Điểm chính", r.narrative.highlights), section("Rủi ro", r.narrative.risks), section("Đề xuất hành động", r.narrative.next_actions),
    h("div", { class: "card" }, h("h3", {}, "Số liệu (ảnh chụp lúc tạo)"),
      h("div", { class: "grid" }, [["Tổng số việc", k.total], ["Đang thực hiện", k.active], ["Tỷ lệ hoàn thành", pct(k.completion_rate)],
        ["Quá hạn", k.overdue], ["Bị chặn", k.blocked], ["Chờ duyệt nhập", k.pending_review]].map(([l, v]) =>
        h("div", { class: "kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l)))),
      h("p", { class: "muted small" }, STATUS_ORDER.filter((s) => k.by_status[s]).map((s) => `${STATUS_LABEL[s]} ${k.by_status[s]}`).join(" · "))),
    h("div", { class: "row" },
      r.status === "DRAFT" && isLeader ? h("button", { class: "btn primary", onclick: async () => {
        try { await api(`/reports/${id}/publish`, { method: "POST" }); await detail(host, me, id); }
        catch (e) { mount(msg, h("div", { class: "msg bad", role: "alert" }, e.message)); } } }, "Duyệt thành báo cáo chính thức") : null,
      r.status === "DRAFT" && !isLeader ? h("span", { class: "muted small" }, "Chỉ trưởng phòng được duyệt báo cáo chính thức.") : null,
      canDelete ? h("button", { class: "btn danger", onclick: async () => {
        try { await api(`/reports/${id}`, { method: "DELETE" }); location.hash = "#/reports"; }
        catch (e) { mount(msg, h("div", { class: "msg bad", role: "alert" }, e.message)); } } }, "Xóa bản nháp") : null,
      h("button", { class: "btn", onclick: () => window.print() }, "In / lưu PDF")));
}

async function list(host, me) {
  const canCreate = ["PM", "DEPT_LEADER"].includes(me.role);
  const msg = h("div", {});
  const box = h("div", { class: "card tablewrap" });
  const llm = h("input", { type: "checkbox" });
  const title = h("input", { placeholder: "Tiêu đề (không bắt buộc)", maxlength: 300 });
  const btn = h("button", { class: "btn primary" }, "Tạo báo cáo nháp");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try { const r = await api("/reports", { method: "POST", body: { title: title.value || null, use_llm: llm.checked } }); location.hash = "#/reports/" + r.id; }
    catch (e) { mount(msg, h("div", { class: "msg bad", role: "alert" }, e.message)); btn.disabled = false; }
  });
  const rows = await api("/reports");
  mount(host, h("h1", {}, "Báo cáo"),
    canCreate ? h("div", { class: "card" }, h("h3", {}, "Tạo báo cáo mới"),
      h("p", { class: "muted small" }, "Số liệu do hệ thống tính từ công việc trong phạm vi của bạn. Gemini (nếu bật) chỉ diễn đạt nhận xét; mọi con số được kiểm tra, sai thì dùng bản mẫu."),
      h("div", { class: "row" }, title, h("label", { class: "row small" }, llm, "Dùng Gemini viết nhận xét"), btn), msg) : null,
    box);
  mount(box, rows.length ? h("table", {},
    h("thead", {}, h("tr", {}, ["Tiêu đề", "Số liệu đến", "Trạng thái", "Cách viết"].map((t) => h("th", {}, t)))),
    h("tbody", {}, rows.map((r) => h("tr", { class: "click", onclick: () => { location.hash = "#/reports/" + r.id; } },
      h("td", {}, r.title), h("td", {}, fmtDate(r.as_of)),
      h("td", {}, h("span", { class: "chip " + (STATUS[r.status] || [])[1] }, (STATUS[r.status] || [r.status])[0])),
      h("td", {}, r.narrative_method === "gemini" ? "Gemini" : "Mẫu"))))) : h("div", { class: "empty" }, "Chưa có báo cáo nào."));
}

export async function reportsView(host, { me, args }) {
  return args[0] ? detail(host, me, args[0]) : list(host, me);
}
