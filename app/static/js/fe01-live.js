/* FE-01 live check-ins and monthly records. Goal progress is deliberately pending. */
(() => {
  "use strict";
  const root = document.querySelector("[data-fe01]"), source = document.getElementById("fe01-sample-config");
  if (!root || !source) return;
  const config = JSON.parse(source.textContent);
  if (config.mode !== "api") return;
  const contract = globalThis.SadariCheckinContract;
  const client = contract.createClient((url, options) => fetch(url, options));
  const find = selector => root.querySelector(selector), all = selector => [...root.querySelectorAll(selector)];
  const format = value => new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 4 }).format(value);
  const won = amount => `${format(amount / 10000)}만 원`;
  const monthLabel = month => `${month.slice(0, 4)}년 ${Number(month.slice(5))}월`;
  const channel = () => ({ ready: false, busy: false, error: "", status: null, message: "", generation: 0, controller: null });
  const state = { paid: null, records: [], dirty: false, weekly: channel(), savings: channel() };
  const input = find("#fe01-amount"), form = find("[data-fe01-month-form]"), chartNode = find("[data-fe01-chart]");
  const chart = chartNode ? window.SadariFe01Chart(chartNode, false) : null;
  const hasWeekly = all("[data-fe01-weekly]").length > 0;
  function setText(selector, value) { const element = find(selector); if (element) element.textContent = value; }
  function controls(kind) {
    const current = state[kind];
    const card = find(kind === "weekly" ? "[data-fe01-week-card]" : "[data-fe01-month-card]");
    card?.setAttribute("aria-busy", String(current.busy));
    const status = find(kind === "weekly" ? "[data-fe01-week-status]" : "[data-fe01-month-status]");
    status?.classList.toggle("is-error", !!current.error);
    const recovery = find(`[data-fe01-recovery="${kind}"]`), paths = { 401: ["/login", "로그인하기"], 403: ["/consent", "필수 동의 확인"], 409: ["/onboarding", "재무 진단하기"] };
    if (recovery) {
      recovery.hidden = !paths[current.status];
      if (!recovery.hidden) { recovery.href = paths[current.status][0]; recovery.textContent = paths[current.status][1]; }
    }
    const retry = find(`[data-fe01-reload="${kind}"]`);
    if (retry) retry.disabled = current.busy;
    if (kind === "weekly") all("[data-fe01-weekly]").forEach(button => { button.disabled = current.busy || !current.ready; });
    else if (form) { input.disabled = current.busy || !current.ready; form.querySelector('[type="submit"]').disabled = current.busy || !current.ready; }
  }
  function renderWeekly() {
    controls("weekly");
    all("[data-fe01-weekly]").forEach(button => button.setAttribute("aria-pressed", String(state.paid === (button.dataset.fe01Weekly === "paid"))));
    const coach = find("[data-fe01-coach]"); if (coach) coach.hidden = state.paid !== false;
    const current = state.weekly;
    setText("[data-fe01-week-status]", current.error || current.message || (state.paid === true ? "이번 주 저축 여부를 저장했어요." : state.paid === false ? "못 냈다고 기록했어요. 다음 계획을 코치와 함께 정해봐요." : "이번 주 저축 여부를 알려 주세요."));
  }
  function renderSavings() {
    controls("savings");
    const current = state.records.find(record => record.month === config.month), channel = state.savings;
    const records = contract.recentRecords(state.records, config.month);
    setText("[data-fe01-month-status]", channel.error || channel.message || (current ? `${config.month_label} 저장 기록: ${won(current.amount)}` : "이번 달 저축 금액을 아직 기록하지 않았어요."));
    setText("[data-fe01-current]", current ? won(current.amount) : "—");
    const index = Number(config.month.slice(0, 4)) * 12 + Number(config.month.slice(5)) - 2;
    const previousMonth = `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}`;
    const previous = state.records.find(record => record.month === previousMonth);
    const difference = current && previous ? current.amount - previous.amount : null;
    setText("[data-fe01-comparison]", difference === null ? (channel.ready ? "비교할 기록이 아직 없어요." : "") : difference > 0 ? `지난달보다 ${won(difference)} 더 모았어요` : difference < 0 ? `지난달보다 ${won(-difference)} 적게 모았어요` : "지난달과 같은 금액이에요");
    // GET /api/savings has no cumulative progress contract yet. Never infer it from 12 displayed months.
    setText("[data-fe01-total]", "—"); setText("[data-fe01-percent]", "진행률 연결 준비 중");
    const emptyText = channel.ready ? "최근 12개월에 저장한 저축 기록이 없어요." : channel.busy ? "저축 기록을 불러오고 있어요." : "기록을 다시 불러와 확인해 주세요.";
    const list = find("[data-fe01-records]");
    if (list) {
      list.replaceChildren();
      [...records].reverse().forEach(record => {
        const row = document.createElement("div"); row.className = "fe01-record";
        const label = document.createElement("span"); label.textContent = monthLabel(record.month);
        const amount = document.createElement("strong"); amount.textContent = won(record.amount);
        row.append(label, amount); list.append(row);
      });
      if (!records.length) { const note = document.createElement("p"); note.className = "field-help"; note.textContent = emptyText; list.append(note); }
    }
    chart?.render(records);
    if (chartNode && !records.length) { const note = document.createElement("p"); note.className = "field-help"; note.textContent = emptyText; chartNode.replaceChildren(note); }
  }
  function syncInput() {
    if (!input || state.dirty) return;
    const current = state.records.find(record => record.month === config.month);
    input.value = current ? String(current.amount / 10000) : "";
  }
  function cancel(kind) { const channel = state[kind]; channel.generation++; channel.controller?.abort(); channel.controller = null; }
  async function run(kind, operation, success, saving) {
    const channel = state[kind]; if (channel.busy) return;
    cancel(kind); const token = channel.generation, controller = new AbortController();
    channel.controller = controller; channel.busy = true; channel.error = ""; channel.status = null;
    channel.message = saving ? "기록을 저장하고 있어요." : "기록을 불러오고 있어요.";
    const render = kind === "weekly" ? renderWeekly : renderSavings; render();
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 20_000);
    try {
      const result = await operation({ signal: controller.signal });
      if (token !== channel.generation) return;
      channel.ready = true; channel.message = ""; success(result);
    } catch (error) {
      if (token !== channel.generation) return;
      channel.status = error.status;
      channel.error = timedOut ? "확인에 시간이 오래 걸리고 있어요. 기록을 다시 불러와 확인해 주세요." : error instanceof TypeError && /fetch|network|load failed/i.test(error.message) ? "인터넷 연결을 확인하고 다시 시도해 주세요." : error.message || "기록을 확인하지 못했어요. 다시 시도해 주세요.";
      if (saving && !channel.error.includes("다시 불러")) channel.error += " 저장 여부는 기록을 다시 불러와 확인해 주세요.";
      if (!saving || [401, 403, 409].includes(error.status)) {
        channel.ready = false;
        if (kind === "weekly") state.paid = null; else { state.records = []; syncInput(); }
      }
    } finally {
      clearTimeout(timeout);
      if (token === channel.generation) { channel.busy = false; channel.controller = null; render(); }
    }
  }
  function loadWeekly() {
    return run("weekly", options => client.loadWeekly(options), records => { state.paid = records.find(record => record.week === config.week)?.paid ?? null; }, false);
  }
  function loadSavings() {
    return run("savings", options => client.loadSavings(options), records => {
      state.records = records;
      const current = records.find(record => record.month === config.month);
      if (state.dirty && current && input) { try { if (contract.parseMan(input.value) === current.amount) state.dirty = false; } catch { /* Keep the user's invalid draft intact. */ } }
      syncInput();
      if (state.dirty) state.savings.message = "저장 기록을 불러왔어요. 입력 중인 금액은 아직 저장되지 않았어요.";
    }, false);
  }
  all("[data-fe01-weekly]").forEach(button => button.addEventListener("click", () => {
    if (!state.weekly.ready) return;
    run("weekly", options => client.saveWeekly(config.week, button.dataset.fe01Weekly === "paid", options), record => { state.paid = record.paid; }, true);
  }));
  form?.addEventListener("submit", event => {
    event.preventDefault(); if (!state.savings.ready || state.savings.busy) return;
    const error = find("#fe01-amount-error"); let amount;
    try { amount = contract.parseMan(input.value); }
    catch (reason) { error.textContent = input.value.trim() ? reason.message : "저축 금액을 입력해 주세요."; error.hidden = false; input.setAttribute("aria-invalid", "true"); input.focus(); return; }
    error.hidden = true; input.removeAttribute("aria-invalid");
    run("savings", options => client.saveSavings(config.month, amount, options), record => {
      state.records = [...state.records.filter(item => item.month !== record.month), record].sort((a, b) => a.month.localeCompare(b.month));
      state.dirty = false; syncInput(); state.savings.message = `${config.month_label} 저축 금액 ${won(record.amount)}을 저장했어요.`;
    }, true);
  });
  input?.addEventListener("input", event => {
    event.stopPropagation(); state.dirty = true;
    try { contract.parseMan(input.value); input.removeAttribute("aria-invalid"); find("#fe01-amount-error").hidden = true; } catch { /* Keep field errors until corrected. */ }
  });
  all("[data-fe01-reload]").forEach(button => button.addEventListener("click", () => button.dataset.fe01Reload === "weekly" ? loadWeekly() : loadSavings()));
  if (hasWeekly) loadWeekly(); loadSavings();
  window.addEventListener("pagehide", () => { cancel("weekly"); cancel("savings"); });
  // Refresh server-rendered account/period context as well as records after back/forward restoration.
  window.addEventListener("pageshow", event => { if (event.persisted) window.location.reload(); });
})();
