/* FE-02 sample adapter: never reads a file, calls an API, or persists financial data. */
(function () {
  "use strict";
  const contract = typeof module !== "undefined" && module.exports
    ? require("./spending-contract.js") : globalThis.SadariSpendingContract;
  const MAX_BYTES = 2 * 1024 * 1024;
  function validateFile(file) {
    if (!file) return "";
    if (!/\.(xlsx|csv)$/i.test(file.name)) return "엑셀(.xlsx) 또는 CSV 파일을 선택해 주세요.";
    if (!file.size) return "빈 파일이에요. 거래내역이 있는 파일을 선택해 주세요.";
    if (file.size > MAX_BYTES) return "2MB 이하의 파일을 선택해 주세요.";
    return "";
  }
  function summarize(base, changes, categories) {
    const rows = base.map(row => ({ ...row, category: categories.includes(changes[row.id]) ? changes[row.id] : row.category }));
    const groups = categories.map(category => ({ category, amount: rows.filter(row => row.category === category).reduce((sum, row) => sum + row.amount, 0) }))
      .filter(group => group.amount > 0).sort((a, b) => b.amount - a.amount);
    const total = rows.reduce((sum, row) => sum + row.amount, 0);
    const fixed = rows.filter(row => row.fixed).reduce((sum, row) => sum + row.amount, 0);
    return { rows, groups, total, fixed, variable: total - fixed, top: [...rows].sort((a, b) => b.amount - a.amount || a.id - b.id).slice(0, 5) };
  }
  if (typeof module !== "undefined" && module.exports) { module.exports = { validateFile, summarize, MAX_BYTES }; return; }
  const root = document.getElementById("spending-page");
  if (!root) return;
  const config = JSON.parse(document.getElementById("spending-preview-config").textContent);
  if (config.mode !== "sample") return;
  const { rows: sampleRows, categories: sampleCategories } = contract.createSampleSource(config).read();
  const find = selector => root.querySelector(selector), all = selector => [...root.querySelectorAll(selector)];
  const format = value => new Intl.NumberFormat("ko-KR").format(value), won = value => format(value) + "원";
  const state = { stage: config.example, categories: {}, expanded: false, fileName: "", progress: 0 };
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let generation = 0, timers = [], chartKey = "", chartSeen = false, observer = null, resetting = false;
  const node = (tag, className, text) => { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; };
  function showChart() {
    if (!find("[data-chart] svg")) return;
    chartSeen = true;
    find("[data-chart]").classList.add("is-revealed");
    observer?.disconnect();
  }
  function drawChart() {
    const chart = find("[data-chart]"), width = Math.floor(chart.getBoundingClientRect().width);
    if (state.stage !== "result" || width < 100) return;
    const groups = summarize(sampleRows, state.categories, sampleCategories).groups;
    const key = width + JSON.stringify(groups);
    if (key === chartKey) return;
    chartKey = key;
    const left = 48, right = 82, rowHeight = 34, height = groups.length * rowHeight + 20;
    const plot = Math.max(30, width - left - right), maximum = Math.max(...groups.map(group => group.amount), 1);
    const make = (tag, attrs, text) => { const element = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value))); if (text !== undefined) element.textContent = text; return element; };
    const svg = make("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "샘플 카테고리별 지출: " + groups.map(group => group.category + " " + won(group.amount)).join(", ") });
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
  }
  function renderResults() {
    const data = summarize(sampleRows, state.categories, sampleCategories);
    find("[data-total]").textContent = format(data.total);
    find("[data-fixed]").textContent = format(data.fixed);
    find("[data-variable]").textContent = format(data.variable);
    const top = find("[data-top-list]"); top.replaceChildren();
    data.top.forEach((row, index) => {
      const element = node("div", "s-rank-row"), middle = node("div", "s-rank-main");
      middle.append(node("strong", "", row.merchant), node("small", "", row.category + " · " + row.date.slice(5).replace("-", ".")));
      element.append(node("span", "s-rank", index + 1), middle, node("span", "s-rank-amount", won(row.amount))); top.append(element);
    });
    all("[data-transaction-row]").forEach((element, index) => { element.hidden = !state.expanded && index >= 5; });
    find("[data-row-count]").textContent = state.expanded ? "전체 10건" : "최근 5건";
    find("[data-more]").textContent = state.expanded ? "간단히 보기" : "나머지 5건 보기";
    drawChart();
  }
  function render() {
    root.dataset.stage = state.stage;
    find("[data-analysis]").hidden = state.stage !== "result";
    find("[data-loading]").hidden = state.stage !== "loading";
    find("[data-await]").hidden = state.stage !== "ready";
    find("[data-empty]").hidden = state.stage !== "empty";
    find("[data-load-error]").hidden = state.stage !== "error";
    find("[data-analysis]").setAttribute("aria-busy", String(state.stage === "loading"));
    find("[data-file-name]").textContent = state.fileName || "샘플_거래내역.csv";
    find("[data-file-help]").textContent = state.fileName ? "이 파일은 읽거나 전송하지 않아요." : "가상의 거래 10건이 준비돼 있어요.";
    find("[data-pick]").disabled = state.stage === "loading";
    find("[data-analyze]").disabled = state.stage === "loading";
    find("[data-progress-fill]").style.width = state.progress + "%";
    find("[data-progress-text]").textContent = state.progress + "%";
    find(".s-progress").setAttribute("aria-valuenow", String(state.progress));
    if (state.stage === "result") renderResults();
  }
  function stop() { generation++; timers.forEach(clearTimeout); timers = []; }
  function analyze() {
    if (state.stage === "loading") return;
    stop(); const token = generation; state.stage = "loading"; state.progress = 0;
    find("[data-file-error]").hidden = true; find("[data-live]").textContent = ""; render();
    [[200, 30], [450, 65], [720, 100]].forEach(([delay, progress]) => timers.push(setTimeout(() => { if (token !== generation) return; state.progress = progress; render(); }, delay)));
    timers.push(setTimeout(() => {
      if (token !== generation) return;
      state.stage = "result"; state.categories = {}; state.expanded = false;
      resetting = true;
      all("[data-transaction]").forEach(select => { select.value = sampleRows.find(row => String(row.id) === select.dataset.transaction).category; select.dataset.changed = "false"; select.dispatchEvent(new Event("change")); });
      resetting = false;
      render(); find("[data-change-status]").textContent = "분류 수정은 이 샘플에만 반영돼요.";
      find("[data-live]").textContent = "샘플 거래 10건의 분석 결과를 준비했어요. 선택한 파일의 실제 분석 결과는 아니에요.";
    }, 850));
  }
  all("[data-transaction]").forEach(select => select.addEventListener("change", () => {
    if (resetting) return;
    const original = sampleRows.find(row => String(row.id) === select.dataset.transaction);
    if (select.value === original.category) delete state.categories[original.id]; else state.categories[original.id] = select.value;
    select.dataset.changed = String(select.value !== original.category);
    renderResults();
    find("[data-change-status]").textContent = original.merchant + " 분류를 ‘" + select.value + "’로 바꿨어요. 이 샘플에만 반영돼요.";
  }));
  if (typeof initProfileSelects === "function") initProfileSelects(root);
  find("[data-pick]").addEventListener("click", () => find("[data-file-input]").click());
  find("[data-file-input]").addEventListener("change", event => {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    const message = validateFile(file), error = find("[data-file-error]");
    if (message) { error.textContent = message; error.hidden = false; return; }
    stop(); state.fileName = file.name; state.stage = "ready"; state.progress = 0; error.hidden = true; render();
    find("[data-live]").textContent = "파일 선택이 끝났어요. 샘플 분석을 시작할 수 있어요.";
  });
  find("[data-analyze]").addEventListener("click", analyze);
  find("[data-retry]").addEventListener("click", analyze);
  find("[data-more]").addEventListener("click", () => {
    state.expanded = !state.expanded; renderResults();
    if (!state.expanded) find(".s-transactions-panel").scrollIntoView({ block: "start", behavior: "auto" });
  });
  render();
  // Hide rows for the stagger only after both the chart and observer are ready.
  try {
    if (!motion.matches && "IntersectionObserver" in window) {
      observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) showChart(); }, { threshold: 0.2 });
      observer.observe(find("[data-chart]")); find("[data-chart]").classList.add("is-motion-ready");
    }
  } catch { showChart(); }
  if ("ResizeObserver" in window) new ResizeObserver(drawChart).observe(find("[data-chart]"));
  else window.addEventListener("resize", drawChart);
  motion.addEventListener?.("change", () => { if (motion.matches) { showChart(); find("[data-chart]").classList.remove("is-motion-ready"); } });
  window.addEventListener("pagehide", stop);
  window.addEventListener("pageshow", event => { if (event.persisted) { if (state.stage === "loading") state.stage = "ready"; render(); showChart(); } });
})();
