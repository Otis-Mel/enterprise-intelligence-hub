import { api } from "../api.js";
import { h, mount, sleep, showError, reviewChip, statusChip, fmtDate, FILE_STATUS_LABEL, STATUS_LABEL, PRIORITY_LABEL, REVIEW_LABEL } from "../util.js";

const FILTERS = ["ALL", "PENDING", "CLEAN", "APPROVED", "REJECTED", "IMPORTED"];

function options(map, selected) {
  return Object.entries(map).map(([k, v]) => h("option", { value: k, selected: k === selected }, v));
}

export async function reviewView(host, { me, args }) {
  const jobId = args[0];
  if (!jobId) { location.hash = "#/imports"; return; }
  const isManager = ["PM", "DEPT_LEADER"].includes(me.role);
  const canNormalize = ["EMPLOYEE", "PM", "DEPT_LEADER"].includes(me.role);

  const job = await api(`/imports/${jobId}`);
  const [directory, projects] = await Promise.all([api("/directory"), isManager ? api("/projects") : Promise.resolve([])]);
  let summary = null, records = [], filter = "ALL", openId = null;

  const msg = h("div", {});
  const top = h("div", {});
  const tabs = h("div", { class: "tabs" });
  const table = h("div", { class: "card tablewrap" });
  const say = (cls, text) => mount(msg, h("div", { class: "msg " + cls, role: cls === "bad" ? "alert" : "status" }, text));

  async function load() {
    try { summary = await api(`/imports/${jobId}/summary`); } catch { summary = null; }
    records = summary && summary.total ? await api(`/imports/${jobId}/records`, { query: { limit: 500 } }) : [];
    draw();
  }

  async function normalize(opts) {
    say("info", "Đang chuẩn hóa…");
    try {
      const r = await api(`/imports/${jobId}/normalize`, { method: "POST", body: opts });
      say("ok", r.note || `Đã chuẩn hóa ${r.total} bản ghi.`);
    } catch (e) { say("bad", e.message); }
    await load();
  }

  function normalizeBox() {
    const llm = h("input", { type: "checkbox" });
    const order = h("select", {}, h("option", { value: "" }, "Tự phát hiện"), h("option", { value: "DMY" }, "Ngày/Tháng/Năm"), h("option", { value: "MDY" }, "Tháng/Ngày/Năm"));
    return h("div", { class: "card" }, h("h3", {}, "Chuẩn hóa"),
      h("p", { class: "muted small" }, "Hệ thống không đoán: giá trị mơ hồ được để trống và đưa vào hàng chờ để người duyệt quyết định."),
      h("div", { class: "row" },
        h("label", { class: "f" }, "Thứ tự ngày", order),
        h("label", { class: "row small" }, llm, "Dùng Gemini cho văn bản tự do (chỉ gợi ý)"),
        h("button", { class: "btn primary", onclick: () => normalize({ date_order: order.value || null, use_llm: llm.checked, force: !!(summary && summary.total) }) },
          summary && summary.total ? "Chuẩn hóa lại" : "Chuẩn hóa")));
  }

  async function approveClean() {
    try { const r = await api(`/imports/${jobId}/approve-clean`, { method: "POST" }); say("ok", `Đã duyệt ${r.approved} bản ghi sạch.`); }
    catch (e) { say("bad", e.message); }
    await load();
  }

  function commitBox() {
    const sel = h("select", {}, projects.map((p) => h("option", { value: p.id }, p.name)));
    const approved = (summary.by_review_status.APPROVED || 0);
    return h("div", { class: "card" }, h("h3", {}, "Đưa vào công việc"),
      projects.length ? h("div", { class: "row" },
        h("label", { class: "f" }, "Dự án đích", sel),
        h("button", { class: "btn primary", disabled: approved === 0, onclick: async () => {
          try { const r = await api(`/imports/${jobId}/commit`, { method: "POST", body: { project_id: sel.value } });
            say("ok", `Mới ${r.created} · cập nhật ${r.updated} · không đổi ${r.unchanged}.`); }
          catch (e) { say("bad", e.message); }
          await load();
        } }, `Nhập ${approved} bản ghi đã duyệt`))
        : h("p", { class: "muted small" }, "Chưa có dự án nào bạn quản lý trong phòng ban. Hãy tạo dự án trước."));
  }

  function editor(r) {
    const editable = isManager && r.review_status !== "IMPORTED";
    const title = h("input", { value: r.title || "", maxlength: 500 });
    const assignee = h("select", {}, h("option", { value: "" }, r.assignee_raw ? `— chưa khớp: ${r.assignee_raw}` : "— không có —"),
      directory.map((u) => h("option", { value: u.id, selected: u.id === r.assignee_id }, u.full_name)));
    const status = h("select", {}, options(STATUS_LABEL, r.status_normalized));
    const prio = h("select", {}, options(PRIORITY_LABEL, r.priority_normalized));
    const progress = h("input", { type: "number", min: 0, max: 100, step: 1, value: r.progress ?? "" });
    const due = h("input", { type: "date", value: r.due_date || "" });
    for (const el of [title, assignee, status, prio, progress, due]) el.disabled = !editable;

    async function save(decision) {
      // chỉ gửi trường người duyệt thực sự đổi (tránh đánh dấu "đã sửa" khi chỉ bấm Duyệt)
      const body = {};
      if (title.value !== (r.title || "")) body.title = title.value;
      if ((assignee.value || null) !== (r.assignee_id || null)) body.assignee_id = assignee.value || null;
      if (status.value !== r.status_normalized) body.status_normalized = status.value;
      if (prio.value !== r.priority_normalized) body.priority_normalized = prio.value;
      if (progress.value !== "" && Number(progress.value) !== r.progress) body.progress = Number(progress.value);
      if (due.value && due.value !== r.due_date) body.due_date = due.value;
      if (decision) body.decision = decision;
      try { await api(`/normalized-records/${r.id}`, { method: "PATCH", body }); mount(msg); }
      catch (e) { say("bad", e.detail && e.detail.issues ? `${e.message} ${e.detail.issues.map((i) => i.message).join("; ")}` : e.message); return; }
      await load();
    }
    return h("div", {},
      h("div", { class: "form" },
        h("label", { class: "f" }, "Tên công việc", title), h("label", { class: "f" }, "Người phụ trách", assignee),
        h("label", { class: "f" }, "Trạng thái", status), h("label", { class: "f" }, "Ưu tiên", prio),
        h("label", { class: "f" }, "Tiến độ (%)", progress), h("label", { class: "f" }, "Hạn", due)),
      r.evidence ? h("div", { class: "evidence" }, h("b", {}, "Trích từ tài liệu: "), r.evidence) : null,
      h("div", { class: "rawbox" }, h("b", {}, "Dữ liệu gốc: "), Object.entries(r.raw || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")),
      r.issues.map((i) => h("div", { class: "issue " + i.severity }, (i.severity === "error" ? "Lỗi: " : "Cảnh báo: ") + i.message)),
      editable ? h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: () => save("APPROVE") }, "Duyệt"),
        h("button", { class: "btn", onclick: () => save(null) }, "Lưu chỉnh sửa"),
        h("button", { class: "btn danger", onclick: () => save("REJECT") }, "Từ chối"),
        ["APPROVED", "REJECTED"].includes(r.review_status) ? h("button", { class: "btn", onclick: () => save("REOPEN") }, "Mở lại") : null)
        : h("p", { class: "muted small" }, isManager ? "Bản ghi đã nhập vào công việc." : "Chỉ PM hoặc trưởng phòng được sửa và duyệt."));
  }

  function draw() {
    mount(top,
      h("div", { class: "row spread" }, h("h1", {}, job.file_name || "Hàng chờ duyệt"),
        h("span", { class: "chip" }, FILE_STATUS_LABEL[(summary && summary.file_status) || job.status] || job.status)),
      canNormalize ? normalizeBox() : null);
    if (!summary || !summary.total) { mount(tabs); mount(commitHost); mount(table, h("div", { class: "empty" }, "Chưa có bản ghi chuẩn hóa. Bấm “Chuẩn hóa” để bắt đầu.")); return; }

    const counts = summary.by_review_status;
    mount(tabs, FILTERS.map((f) => h("button", { class: f === filter ? "on" : "", onclick: () => { filter = f; draw(); } },
      `${f === "ALL" ? "Tất cả" : REVIEW_LABEL[f]} (${f === "ALL" ? summary.total : counts[f] || 0})`)),
      isManager && (counts.CLEAN || 0) > 0 ? h("button", { class: "btn", onclick: approveClean }, `Duyệt ${counts.CLEAN} bản ghi sạch`) : null);

    const rows = records.filter((r) => filter === "ALL" || r.review_status === filter);
    mount(table, rows.length ? h("table", {},
      h("thead", {}, h("tr", {}, ["#", "Công việc", "Người phụ trách", "Trạng thái", "Hạn", "Tình trạng", "Vấn đề"].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.flatMap((r) => {
        const main = h("tr", { class: "click", onclick: () => { openId = openId === r.id ? null : r.id; draw(); } },
          h("td", {}, r.row_ref), h("td", {}, r.title || h("i", { class: "muted" }, "(trống)")), h("td", {}, r.assignee_raw || "—"),
          h("td", {}, statusChip(r.status_normalized)), h("td", {}, fmtDate(r.due_date)), h("td", {}, reviewChip(r.review_status)),
          h("td", {}, r.issues.length ? h("span", { class: "chip " + (r.issues.some((i) => i.severity === "error") ? "bad" : "warn") }, `${r.issues.length}`) : "—"));
        return openId === r.id ? [main, h("tr", { class: "detail" }, h("td", { colspan: 7 }, editor(r)))] : [main];
      }))) : h("div", { class: "empty" }, "Không có bản ghi trong mục này."));
    // commit box ở cuối
    mount(commitHost, isManager ? commitBox() : null);
  }

  const commitHost = h("div", {});
  mount(host, top, msg, tabs, table, commitHost);
  await load();
}
