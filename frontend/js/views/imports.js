import { api } from "../api.js";
import { h, mount, sleep, showError, fmtDate, FILE_STATUS_LABEL } from "../util.js";

const EXTS = ".csv,.xlsx,.xlsm,.docx,.pdf,.txt";

async function waitForImport(jobId, onTick) {
  for (let i = 0; i < 120; i++) {
    const j = await api(`/imports/${jobId}`);
    onTick(j);
    if (!["UPLOADED", "PARSING"].includes(j.status)) return j;
    await sleep(1000);
  }
  throw new Error("Quá thời gian chờ đọc file.");
}

export async function importsView(host, { me }) {
  const canUpload = ["EMPLOYEE", "PM", "DEPT_LEADER"].includes(me.role);
  const status = h("div", {});
  const list = h("div", { class: "card tablewrap" });

  async function refresh() {
    const rows = await api("/imports");
    mount(list, rows.length ? h("table", {},
      h("thead", {}, h("tr", {}, ["File", "Ngày tải", "Trạng thái", "Số dòng đọc được", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.map((j) => h("tr", { class: "click", onclick: () => { location.hash = "#/review/" + j.job_id; } },
        h("td", {}, j.file_name), h("td", {}, fmtDate(j.created_at)),
        h("td", {}, h("span", { class: "chip " + (j.status === "FAILED" ? "bad" : j.status === "IMPORTED" ? "ok" : "info") }, FILE_STATUS_LABEL[j.status] || j.status),
          j.error_summary ? h("div", { class: "small muted" }, j.error_summary) : null),
        h("td", {}, j.records_read), h("td", {}, h("a", { href: "#/review/" + j.job_id }, "Mở")))))) : h("div", { class: "empty" }, "Chưa có lần nhập nào."));
  }

  const input = h("input", { type: "file", accept: EXTS, "aria-label": "Chọn file" });
  const btn = h("button", { class: "btn primary" }, "Tải lên và đọc file");
  btn.addEventListener("click", async () => {
    if (!input.files.length) return mount(status, h("div", { class: "msg bad" }, "Hãy chọn một file."));
    btn.disabled = true;
    try {
      const fd = new FormData(); fd.append("file", input.files[0]);
      mount(status, h("div", { class: "msg info" }, "Đang tải lên…"));
      const f = await api("/files/upload", { method: "POST", form: fd });
      const job = await api("/imports", { method: "POST", body: { file_id: f.id } });
      const done = await waitForImport(job.id, (j) => mount(status, h("div", { class: "msg info" }, `Đang đọc file… (${FILE_STATUS_LABEL[j.status] || j.status})`)));
      if (done.status === "FAILED") throw new Error(done.error_summary || "Đọc file thất bại.");
      location.hash = "#/review/" + done.id;
    } catch (e) { mount(status, h("div", { class: "msg bad", role: "alert" }, e.message)); btn.disabled = false; await refresh(); }
  });

  mount(host, h("h1", {}, "Nhập dữ liệu"),
    canUpload ? h("div", { class: "card" }, h("h3", {}, "Tải file mới"),
      h("p", { class: "muted small" }, "Hỗ trợ Excel, CSV, Word, PDF (có chữ). Dữ liệu chỉ vào hệ thống sau khi người có trách nhiệm duyệt."),
      h("div", { class: "row" }, input, btn), status) : null,
    h("h2", {}, "Các lần nhập"), list);
  await refresh();
}
