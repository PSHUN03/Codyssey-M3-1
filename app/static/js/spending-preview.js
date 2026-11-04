/* DATA-06 file preview only. Never writes transactions or calls BE-01 endpoints. */
(() => {
  "use strict";
  const contract = typeof module !== "undefined" && module.exports
    ? require("./spending-contract.js") : globalThis.SadariSpendingContract;
  const PAGE_SIZE = 20;
  const categories = contract.CATEGORIES.filter(category => category !== "수입");
  function summarizePreview(preview, changes = {}) {
    const rows = preview.expenses.map(row => ({ ...row, category: categories.includes(changes[row.previewIndex]) ? changes[row.previewIndex] : row.category }));
    return { total: preview.totalSpending,
      groups: categories.map(category => ({ category, amount: rows.filter(row => row.category === category).reduce((sum, row) => sum + row.amount, 0) })).filter(row => row.amount > 0).sort((a, b) => b.amount - a.amount),
      top: [...rows].sort((a, b) => b.amount - a.amount || a.previewIndex - b.previewIndex).slice(0, 5) };
  }
  if (typeof module !== "undefined" && module.exports) { module.exports = { summarizePreview, PAGE_SIZE }; return; }
  const root = document.getElementById("spending-page");
  if (!root || JSON.parse(document.getElementById("spending-preview-config").textContent).mode !== "preview") return;
  const previewFile = contract.createPreviewClient((url, init) => fetch(url, init));
  const find = selector => root.querySelector(selector), all = selector => [...root.querySelectorAll(selector)];
  const format = value => new Intl.NumberFormat("ko-KR").format(value), won = value => format(value) + "원";
  const state = { stage: "idle", file: null, preview: null, changes: {}, page: 0, error: "", errorStatus: null, lastOptions: {} };
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)"), rowPool = [];
  let generation = 0, controller = null, mappingController = null, resetting = false;
  let chartKey = "", chartSeen = false, observer = null;
  const node = (tag, className, text) => { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; };
  const announce = text => { find("[data-live]").textContent = text; };
  const summary = () => summarizePreview(state.preview, state.changes);
  function showChart() {
    if (!find("[data-chart] svg")) return;
    chartSeen = true; find("[data-chart]").classList.add("is-revealed"); observer?.disconnect();
  }
  function resetChart() {
    chartKey = ""; chartSeen = false; observer?.disconnect();
    find("[data-chart]").classList.remove("is-revealed", "is-settled", "is-motion-ready");
  }
  function drawChart() {
    const chart = find("[data-chart]"), width = Math.floor(chart.getBoundingClientRect().width);
    if (state.stage !== "result" || width < 100) return;
    const groups = summary().groups, key = width + JSON.stringify(groups);
    if (key === chartKey) return;
    chartKey = key;
    if (!groups.length) { chart.replaceChildren(node("p", "s-panel-sub", "이 파일에는 지출 내역이 없어요.")); return; }
    const left = 48, right = 90, rowHeight = 34, height = groups.length * rowHeight + 20;
    const plot = Math.max(30, width - left - right), maximum = Math.max(...groups.map(group => group.amount), 1);
    const make = (tag, attrs, text) => { const element = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value))); if (text !== undefined) element.textContent = text; return element; };
    const svg = make("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "미리보기 카테고리별 지출: " + groups.map(group => group.category + " " + won(group.amount)).join(", ") });
    groups.forEach((group, index) => {
      const y = 9 + index * rowHeight, row = make("g", { "data-chart-row": group.category, style: `--row-delay:${index * 65}ms` });
      row.append(make("text", { x: 0, y: y + 13 }, group.category),
        make("rect", { x: left, y, width: plot, height: 16, rx: 5, fill: "var(--s-pale)" }),
        make("rect", { x: left, y, width: Math.max(2, group.amount / maximum * plot), height: 16, rx: 5, fill: "var(--s-purple)", "data-category-bar": group.category, "data-amount": group.amount }),
        make("text", { x: width - 1, y: y + 13, "text-anchor": "end", class: "s-chart-amount" }, won(group.amount)));
      svg.append(row);
    });
    chart.replaceChildren(svg);
    if (chartSeen) chart.classList.add("is-settled");
    else if (!motion.matches && "IntersectionObserver" in window) {
      try {
        observer?.disconnect(); observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) showChart(); }, { threshold: 0.2 });
        observer.observe(chart); chart.classList.add("is-motion-ready");
      } catch { showChart(); }
    }
  }
  function createRowPool() {
    const body = find("[data-rows]");
    for (let index = 0; index < PAGE_SIZE; index++) {
      const row = node("tr"), date = node("td", "s-date"), merchant = node("td", "s-merchant"), amount = node("td", "s-amount"), field = node("td");
      row.hidden = true;
      const label = node("label", "sr-only", "거래 분류"), select = node("select", "s-category"), income = node("span", "s-income", "수입");
      select.id = `spending-category-slot-${index}`; label.htmlFor = select.id;
      select.dataset.profileSelect = ""; select.dataset.transaction = "";
      categories.forEach(category => { const option = node("option", "", category); option.value = category; select.append(option); });
      field.append(label, select, income); row.append(date, merchant, amount, field); body.append(row);
      rowPool.push({ row, date, merchant, amount, field, label, select, income });
    }
  }
  function renderTransactions() {
    const rows = state.preview.transactions, start = state.page * PAGE_SIZE;
    rowPool.forEach((slot, index) => {
      const transaction = rows[start + index]; slot.row.hidden = !transaction;
      if (!transaction) return;
      const expense = transaction.amount < 0, category = state.changes[transaction.previewIndex] || transaction.category;
      slot.row.dataset.transactionRow = String(transaction.previewIndex);
      slot.date.textContent = transaction.date;
      slot.merchant.textContent = transaction.merchant || "거래처 정보 없음";
      slot.amount.textContent = (expense ? "−" : "+") + won(Math.abs(transaction.amount));
      slot.income.hidden = expense; slot.field.classList.toggle("is-income", !expense);
      slot.select.dataset.transaction = String(transaction.previewIndex); slot.select.value = category;
      slot.select.dataset.changed = String(category !== transaction.category);
      slot.label.textContent = (transaction.merchant || "거래처 정보 없음") + " 거래 분류";
      slot.select.dispatchEvent(new Event("change"));
    });
    find("[data-row-count]").textContent = `${start + 1}~${Math.min(start + PAGE_SIZE, rows.length)} / ${format(rows.length)}건`;
    find("[data-previous]").hidden = state.page === 0;
    find("[data-more]").hidden = start + PAGE_SIZE >= rows.length;
    find("[data-more]").textContent = "다음 거래";
  }
  function renderResults() {
    const data = summary();
    find("[data-total]").textContent = format(data.total);
    find("[data-fixed]").textContent = "—"; find("[data-variable]").textContent = "—";
    find("[data-total-note]").textContent = `출금 ${format(state.preview.expenses.length)}건 · 입금은 지출에서 제외했어요.`;
    const top = find("[data-top-list]"); top.replaceChildren();
    if (!data.top.length) top.append(node("p", "s-panel-sub", "표시할 지출이 없어요."));
    data.top.forEach((row, index) => {
      const element = node("div", "s-rank-row"), middle = node("div", "s-rank-main");
      middle.append(node("strong", "", row.merchant || "거래처 정보 없음"), node("small", "", row.category + " · " + row.date.slice(5).replace("-", ".")));
      element.append(node("span", "s-rank", index + 1), middle, node("span", "s-rank-amount", won(row.amount))); top.append(element);
    });
    resetting = true; renderTransactions(); resetting = false; drawChart();
  }
  function render() {
    root.dataset.stage = state.stage;
    for (const [selector, stage] of [["analysis", "result"], ["loading", "loading"], ["idle", "idle"], ["await", "ready"], ["empty", "empty"], ["load-error", "error"], ["mapping", "mapping"], ["partial", "partial"]]) find(`[data-${selector}]`).hidden = state.stage !== stage;
    find(".s-upload-panel").setAttribute("aria-busy", String(state.stage === "loading"));
    find("[data-file-name]").textContent = state.file?.name || "거래내역 파일을 선택해 주세요";
    find("[data-file-help]").textContent = state.file ? "선택한 파일의 내용을 확인해요. 아직 저장되지 않아요." : "파일 선택 후 미리보기를 눌러 주세요.";
    find("[data-analyze]").disabled = state.stage === "loading" || !state.file;
    find("[data-retry]").disabled = !state.file;
    find(".s-progress").classList.add("is-indeterminate");
    find(".s-progress").removeAttribute("aria-valuenow");
    find("[data-progress-fill]").style.width = "35%";
    find("[data-progress-text]").textContent = "잠시만 기다려 주세요";
    find("[data-error-message]").textContent = state.error;
    const recovery = find("[data-recovery]"), recoveries = { 401: ["/login?next=%2Fspending", "로그인하기"], 403: ["/consent", "필수 동의 확인"], 409: ["/onboarding", "재무 진단하기"] };
    recovery.hidden = !recoveries[state.errorStatus];
    if (!recovery.hidden) { recovery.href = recoveries[state.errorStatus][0]; recovery.textContent = recoveries[state.errorStatus][1]; }
    if (state.stage === "result") renderResults();
  }
  function stop() { generation++; controller?.abort(); controller = null; }
  function resultReady() {
    state.changes = {}; state.page = 0; resetChart(); state.stage = "result"; render();
    find("[data-change-status]").textContent = "분류 변경과 거래내역은 아직 저장되지 않아요.";
  }
  function showMapping(preview) {
    mappingController?.abort(); mappingController = new AbortController();
    const table = find("[data-mapping-table]"); table.replaceChildren();
    const width = Math.max(0, ...preview.map(row => row.length)), head = node("thead"), heading = node("tr");
    heading.append(node("th", "", "행"));
    for (let col = 0; col < width; col++) heading.append(node("th", "", `${col + 1}열`));
    head.append(heading); const body = node("tbody");
    preview.forEach((row, index) => { const tr = node("tr"); tr.append(node("th", "", index + 1)); for (let col = 0; col < width; col++) tr.append(node("td", "", row[col] || "")); body.append(tr); });
    table.append(head, body);
    const fields = find("[data-mapping-fields]"); fields.replaceChildren();
    const options = preview.map((_, index) => [index, `${index + 1}행`]);
    const fieldsToShow = [["header", "제목 행", options], ...[["date", "거래일 · 필수"], ["merchant", "거래처 · 필수"], ["withdrawal", "출금액"], ["deposit", "입금액"], ["amount", "금액"], ["direction", "입출금 구분"]].map(([key, label]) => [key, label, Array.from({ length: width }, (_, index) => [index, `${index + 1}열`])])];
    fieldsToShow.forEach(([key, title, choices]) => {
      const field = node("div"), label = node("label", "s-panel-sub", title), select = node("select", "s-category");
      select.id = "spending-mapping-" + key; select.name = key; label.htmlFor = select.id; select.dataset.profileSelect = "";
      if (key !== "header") { const blank = node("option", "", "선택 안 함"); blank.value = ""; select.append(blank); }
      choices.forEach(([value, title]) => { const option = node("option", "", title); option.value = value; select.append(option); });
      field.append(label, select); fields.append(field);
    });
    find("[data-mapping-error]").hidden = true;
    if (typeof initProfileSelects === "function") initProfileSelects(fields, mappingController.signal);
  }
  function showPartial() {
    const data = state.preview, list = find("[data-row-errors]"); list.replaceChildren();
    find("[data-partial-summary]").textContent = `정상 ${format(data.transactions.length)}건 · 오류 ${format(data.errors.length)}건`;
    data.errors.slice(0, 20).forEach(error => list.append(node("li", "", `${error.row}행: ${error.reason}`)));
    if (data.errors.length > 20) list.append(node("li", "", `외 ${format(data.errors.length - 20)}건의 오류가 있어요.`));
    find("[data-confirm-partial]").disabled = !data.transactions.length;
  }
  async function analyze(options = {}) {
    if (state.stage === "loading" || !state.file) return;
    stop(); const token = generation; state.stage = "loading"; state.errorStatus = null;
    find("[data-file-error]").hidden = true; announce(""); render();
    state.lastOptions = options; controller = new AbortController(); let timedOut = false;
    const currentController = controller;
    const timeout = setTimeout(() => { timedOut = true; currentController.abort(); }, 60_000);
    try {
      const data = await previewFile(state.file, { ...options, signal: currentController.signal });
      if (token !== generation) return;
      state.preview = data;
      if (data.status === "mapping-required") { showMapping(data.preview); state.stage = "mapping"; }
      else if (data.status === "partial") { showPartial(); state.stage = "partial"; }
      else if (data.status === "empty") state.stage = "empty";
      else resultReady();
      render();
      if (state.stage === "mapping") find("#spending-mapping-title").focus({ preventScroll: true });
      else if (state.stage === "partial") find("#spending-partial-title").focus({ preventScroll: true });
      else announce(state.stage === "empty" ? "변환된 거래가 없어요. 파일 내용을 확인해 주세요." : `거래 ${format(data.transactions.length)}건의 미리보기를 준비했어요. 아직 저장되지 않았어요.`);
    } catch (error) {
      if (token !== generation) return;
      state.stage = "error"; state.errorStatus = error.status;
      state.error = timedOut ? "확인에 시간이 오래 걸리고 있어요. 잠시 후 다시 시도해 주세요." : error instanceof TypeError && /fetch|network|load failed/i.test(error.message) ? "인터넷 연결을 확인한 뒤 다시 시도해 주세요." : error.message || "미리보기를 불러오지 못했어요. 다시 시도해 주세요.";
      render();
    } finally { clearTimeout(timeout); if (controller === currentController) controller = null; }
  }
  createRowPool();
  all("[data-transaction]").forEach(select => select.addEventListener("change", () => {
    if (resetting || state.stage !== "result") return;
    const original = state.preview.expenses.find(row => String(row.previewIndex) === select.dataset.transaction);
    if (!original) return;
    if (select.value === original.category) delete state.changes[original.previewIndex]; else state.changes[original.previewIndex] = select.value;
    renderResults(); find("[data-change-status]").textContent = original.merchant + " 분류를 ‘" + select.value + "’로 바꿨어요. 현재 미리보기에만 반영되며 저장되지 않아요.";
  }));
  if (typeof initProfileSelects === "function") initProfileSelects(root);
  find("[data-pick]").addEventListener("click", () => find("[data-file-input]").click());
  all("[data-reselect]").forEach(button => button.addEventListener("click", () => find("[data-file-input]").click()));
  find("[data-file-input]").addEventListener("change", event => {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    let message = "";
    try { contract.buildPreviewRequest(file); } catch (error) { message = error.message; }
    const error = find("[data-file-error]");
    if (message) { error.textContent = message; error.hidden = false; return; }
    stop(); mappingController?.abort(); state.file = file; state.stage = "ready"; state.preview = null; state.lastOptions = {}; error.hidden = true; render();
    announce("파일 선택이 끝났어요. 미리보기를 눌러 내용을 확인해 주세요.");
  });
  find("[data-analyze]").addEventListener("click", () => analyze());
  find("[data-retry]").addEventListener("click", () => analyze(state.lastOptions));
  find("[data-confirm-partial]").addEventListener("click", () => { if (!state.preview?.transactions.length) return; resultReady(); announce("오류 행을 제외한 정상 거래만 표시했어요. 아직 저장되지 않았어요."); });
  find("[data-mapping-fields]").addEventListener("change", () => { find("[data-mapping-error]").hidden = true; });
  find("[data-mapping-form]").addEventListener("submit", event => {
    event.preventDefault(); const form = event.currentTarget, mapping = {};
    for (const key of ["date", "merchant", "withdrawal", "deposit", "amount", "direction"]) if (form.elements[key].value !== "") mapping[key] = Number(form.elements[key].value);
    const options = { mapping, headerRow: Number(form.elements.header.value) }, error = find("[data-mapping-error]");
    try {
      if ("amount" in mapping && ("withdrawal" in mapping || "deposit" in mapping)) throw new Error("출금액·입금액 또는 금액 중 한 가지 방식을 선택해 주세요.");
      if (Object.values(mapping).some(column => column >= (state.preview.preview[options.headerRow]?.length || 0))) throw new Error("선택한 제목 행에 있는 열을 골라 주세요.");
      contract.buildPreviewRequest(state.file, options); error.hidden = true; analyze(options);
    } catch (reason) { error.textContent = reason.message; error.hidden = false; }
  });
  find("[data-more]").addEventListener("click", () => { state.page++; renderResults(); find(".s-transactions-panel").scrollIntoView({ block: "start", behavior: "auto" }); });
  find("[data-previous]").addEventListener("click", () => { state.page = Math.max(0, state.page - 1); renderResults(); find(".s-transactions-panel").scrollIntoView({ block: "start", behavior: "auto" }); });
  render();
  if ("ResizeObserver" in window) new ResizeObserver(drawChart).observe(find("[data-chart]"));
  else window.addEventListener("resize", drawChart);
  motion.addEventListener?.("change", () => { if (motion.matches) { showChart(); find("[data-chart]").classList.remove("is-motion-ready"); } });
  window.addEventListener("pagehide", stop);
  window.addEventListener("pageshow", event => { if (event.persisted) { if (state.stage === "loading") state.stage = "ready"; render(); showChart(); } });
})();
