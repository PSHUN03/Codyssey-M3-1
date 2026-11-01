/* 사다리 프런트엔드. 페이지별 동작은 body[data-page]로 나눈다. 외부 라이브러리 없이 동작한다. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function toast(message) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, { method = "GET", body, signal } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
    signal,
  });
  if (res.status === 401) { location.href = "/login"; throw new Error("로그인이 필요해요."); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? "입력한 값을 확인해 주세요." : data.detail;
    throw new Error(detail || "요청을 처리하지 못했어요.");
  }
  return data;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* 서버의 render_md(app/web.py)와 같은 규칙: HTML 이스케이프 → **굵게** → 줄바꿈 */
function renderMd(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
}

/* 서버의 fmt_won과 같은 표기: 2450000 → "245만 원", 1387500 → "138만 7,500원" */
function won(n) {
  if (n === null || n === undefined) return "-";
  const v = Math.round(n);
  const eok = Math.floor(v / 1e8), man = Math.floor((v % 1e8) / 1e4), rest = v % 1e4;
  const parts = [];
  if (eok) parts.push(`${eok.toLocaleString("ko-KR")}억`);
  if (man) parts.push(`${man.toLocaleString("ko-KR")}만`);
  if (rest) parts.push(rest.toLocaleString("ko-KR"));
  if (!parts.length) return "0원";
  return parts.join(" ") + (rest ? "원" : " 원");
}

const digits = (value) => String(value ?? "").replace(/[^\d]/g, "");
const toWon = (manwon) => Math.round(Number(manwon) * 10000);

// 숫자 입력칸은 숫자만 남긴다 (type="number"의 스피너·지수 표기를 피하려고 text + inputmode를 쓴다)
document.addEventListener("input", (ev) => {
  const el = ev.target;
  if (el.matches?.('input[inputmode="numeric"]')) {
    const clean = digits(el.value).slice(0, 7);
    if (clean !== el.value) el.value = clean;
  }
});

/* ------------------------------------------------------------ 랜딩: 월급 계산기 */
function initLanding() {
  const form = $("#calc-form");
  if (!form) return;
  const rentField = $("#calc-rent"), row = $("#calc-row");
  const amountEl = $("#calc-amount"), bar = $("#calc-bar"), legend = $("#calc-legend"), extra = $("#calc-extra");
  const kinds = { fixed: "k-fixed", living: "k-living", saving: "k-saving" };
  let timer, controller;

  const read = (name) => digits(form.elements[name].value);

  function render(d) {
    amountEl.textContent = won(d.total_saving);
    bar.innerHTML = d.groups.filter((g) => g.amount > 0)
      .map((g) => `<span class="${kinds[g.key]}" style="flex:${g.amount}"></span>`).join("");
    legend.innerHTML = d.groups
      .map((g) => `<li><span class="dot ${kinds[g.key]}"></span>${escapeHtml(g.label)}<span class="amt">${won(g.amount)}</span></li>`)
      .join("");
    extra.classList.toggle("is-warn", Boolean(d.warning));
    if (d.warning) extra.textContent = d.warning;
    else if (d.contribution_label) extra.textContent = `조건이 맞으면 청년미래적금으로 3년간 정부기여금 약 ${d.contribution_label}을 더 받을 수 있어요.`;
    else extra.textContent = "";
  }

  async function update() {
    const withParents = form.elements.living.value === "parents";
    rentField.hidden = withParents;
    row.classList.toggle("is-single", withParents);
    const income = read("monthly_income");
    if (!income) {
      amountEl.textContent = "월급을 적어 주세요";
      bar.innerHTML = legend.innerHTML = extra.textContent = "";
      return;
    }
    controller?.abort();
    controller = new AbortController();
    try {
      const d = await api("/api/public/quick-plan", {
        method: "POST",
        signal: controller.signal,
        body: {
          monthly_income: toWon(income),
          rent: withParents ? 0 : toWon(read("rent") || 0),
          fixed_costs: toWon(read("fixed_costs") || 0),
          with_parents: withParents,
        },
      });
      render(d);
    } catch (e) {
      if (e.name !== "AbortError") { extra.classList.add("is-warn"); extra.textContent = "금액을 다시 확인해 주세요."; }
    }
  }

  form.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(update, 250); });
  form.addEventListener("change", update);
  form.addEventListener("submit", (ev) => ev.preventDefault());
  update();
}

/* ------------------------------------------------------------ 재무 진단: 질문 카드 */
function initOnboarding() {
  const card = $("#ob-card"), back = $("#ob-back"), bar = $("#ob-bar"), count = $("#ob-count");
  let questions = [], answers = {}, current = 0, view = "question", editing = false;

  const has = (key) => Object.prototype.hasOwnProperty.call(answers, key);
  const stages = [
    { label: "내 수입 알아보기", keys: new Set(["age", "employment_type", "company_size", "monthly_income", "annual_income"]) },
    { label: "내 지출 살펴보기", keys: new Set(["housing_type", "rent", "fixed_costs", "has_debt", "debt_total", "debt_monthly", "savings", "saving_monthly"]) },
    { label: "저축 목표 정하기", keys: new Set(["region", "goal"]) },
  ];
  const stageIndex = (q) => Math.max(0, stages.findIndex((stage) => stage.keys.has(q.key)));
  const byKey = (key) => questions.find((q) => q.key === key);
  const isVisible = (q) => !q.when || Object.entries(q.when).every(([k, vals]) => vals.includes(answers[k]));
  const visible = () => questions.filter(isVisible);
  const errorEl = () => $("#ob-error", card);

  function setProgress() {
    const list = visible();
    if (view === "summary") {
      bar.style.width = "100%";
      count.textContent = "확인";
      back.classList.remove("is-hidden");
      return;
    }
    const q = questions[current];
    const pos = list.indexOf(q);
    const stage = stageIndex(q);
    const inStage = list.filter((item) => stageIndex(item) === stage);
    const stagePos = Math.max(0, inStage.indexOf(q));
    const progress = (stage + (stagePos + 1) / Math.max(inStage.length, 1)) / stages.length;
    bar.style.width = `${progress * 100}%`;
    count.textContent = `${stages[stage].label} ${stage + 1}/3`;
    document.querySelectorAll(".ob-steps li").forEach((item, index) => {
      item.classList.toggle("is-current", index === stage);
      if (index === stage) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
    back.classList.toggle("is-hidden", pos === 0 && view === "question");
  }

  function actions(primary, q) {
    const skip = q && q.optional
      ? `<button class="btn btn-ghost btn-lg" type="button" data-ob="skip">${escapeHtml(q.skip_label || "건너뛰기")}</button>` : "";
    return `<div class="ob-actions"><button class="btn btn-primary btn-lg" type="button" data-ob="${primary[0]}">${primary[1]}</button>${skip}</div>`;
  }

  function inputHtml(q) {
    const unit = q.type === "amount" ? "만 원" : (q.unit || "");
    const value = has(q.key) && answers[q.key] !== null ? answers[q.key] : "";
    return `<label class="sr-only" for="ob-input">${escapeHtml(q.title)}</label>
      <div class="big-input"><input id="ob-input" inputmode="numeric" autocomplete="off"
        placeholder="${escapeHtml(q.placeholder || "")}" value="${escapeHtml(value)}"><span class="unit">${unit}</span></div>
      <p class="ob-hint" id="ob-hint"></p><p class="ob-error" id="ob-error" role="alert"></p>
      ${actions(["next", "다음"], q)}`;
  }

  function choicesHtml(q) {
    const buttons = q.options.map(([value, label]) =>
      `<button type="button" class="choice" data-value="${escapeHtml(value)}" aria-pressed="${has(q.key) && answers[q.key] === value}">${escapeHtml(label)}</button>`
    ).join("");
    return `<div class="choices${q.columns === 3 ? " cols-3" : ""}" role="group" aria-labelledby="ob-title">${buttons}</div>`;
  }

  function textHtml(q) {
    const goal = answers.goal;
    return `<label class="sr-only" for="ob-text">${escapeHtml(q.title)}</label>
      <input type="text" id="ob-text" maxlength="100" placeholder="${escapeHtml(q.placeholder || "")}" value="${escapeHtml(goal ? goal.goal_text : "")}">
      <p class="ob-error" id="ob-error" role="alert"></p>
      ${actions(["next", "다음"], q)}`;
  }

  function show(index) {
    current = index;
    view = "question";
    const q = questions[current];
    setProgress();
    const body = q.type === "choice" ? choicesHtml(q) : q.type === "text" ? textHtml(q) : inputHtml(q);
    card.innerHTML = `<h1 class="ob-title" id="ob-title">${escapeHtml(q.title)}</h1>
      ${q.help ? `<p class="ob-help">${escapeHtml(q.help)}</p>` : ""}<div class="ob-body">${body}</div>`;
    const input = $("#ob-input, #ob-text", card);
    if (input) { input.focus(); updateHint(); } else card.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  function updateHint() {
    const q = questions[current], hint = $("#ob-hint", card), input = $("#ob-input", card);
    if (!hint || !input) return;
    const v = digits(input.value);
    hint.textContent = q.type === "amount" && v ? `${toWon(v).toLocaleString("ko-KR")}원` : "";
  }

  function next() {
    const list = visible();
    if (editing) {
      const missing = list.find((q) => !has(q.key));
      return missing ? show(questions.indexOf(missing)) : renderSummary();
    }
    const pos = list.indexOf(questions[current]);
    return pos + 1 < list.length ? show(questions.indexOf(list[pos + 1])) : renderSummary();
  }

  function prev() {
    const list = visible();
    if (view === "summary") return show(questions.indexOf(list[list.length - 1]));
    if (view === "goal") return show(current);
    const pos = list.indexOf(questions[current]);
    if (pos > 0) show(questions.indexOf(list[pos - 1]));
  }

  function readInput(q) {
    const raw = digits($("#ob-input", card).value);
    if (raw === "") return q.optional ? { value: null } : { error: "숫자를 적어 주세요." };
    const v = Number(raw);
    if (q.type === "number") {
      return v < q.min || v > q.max ? { error: `${q.min}~${q.max} 사이로 적어 주세요.` } : { value: v };
    }
    if (!q.allow_zero && v === 0) return { error: "0보다 큰 금액을 적어 주세요." };
    if (q.min && v < q.min) return { error: `${q.min.toLocaleString("ko-KR")}만 원 이상으로 적어 주세요. 단위는 만 원이에요.` };
    if (q.max && v > q.max) return { error: "금액이 너무 커요. 단위가 만 원인지 확인해 주세요." };
    return { value: v };
  }

  function pick(btn) {
    const q = questions[current];
    $$(".choice", card).forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    answers[q.key] = btn.dataset.value;
    clearTimeout(pick.timer);
    pick.timer = setTimeout(next, 160);
  }

  function onNext(btn) {
    const q = questions[current];
    if (q.type === "text") return parseGoal(btn, q);
    const r = readInput(q);
    if (r.error) { errorEl().textContent = r.error; $("#ob-input", card).focus(); return; }
    answers[q.key] = r.value;
    next();
  }

  function onSkip() {
    answers[questions[current].key] = null;
    next();
  }

  async function parseGoal(btn, q) {
    const text = $("#ob-text", card).value.trim();
    if (!text) { errorEl().textContent = `목표를 적거나 '${q.skip_label}'를 눌러 주세요.`; return; }
    btn.disabled = true;
    btn.textContent = "읽고 있어요";
    try {
      renderGoal(await api("/api/onboarding/parse-goal", { method: "POST", body: { text } }));
    } catch (e) {
      errorEl().textContent = e.message;
      btn.disabled = false;
      btn.textContent = "다음";
    }
  }

  function renderGoal(result) {
    view = "goal";
    setProgress();
    const g = result.goal || {};
    const amount = g.goal_amount ? Math.round(g.goal_amount / 10000) : "";
    card.innerHTML = `<h1 class="ob-title" id="ob-title">${result.ok ? "이렇게 이해했어요" : "금액과 기간을 적어 주세요"}</h1>
      <p class="ob-help">${result.ok ? "다르면 고쳐 주세요." : escapeHtml(result.message || "")}</p>
      <div class="ob-body ob-goal">
        <label class="field"><span class="field-label">목표</span>
          <input type="text" id="goal-text" maxlength="100" value="${escapeHtml(g.goal_text || "")}"></label>
        <div class="pair">
          <label class="field"><span class="field-label">금액</span>
            <span class="money-input"><input id="goal-amount" inputmode="numeric" autocomplete="off" value="${amount}"><span class="unit">만 원</span></span></label>
          <label class="field"><span class="field-label">기간</span>
            <span class="money-input"><input id="goal-months" inputmode="numeric" autocomplete="off" value="${g.goal_months || ""}"><span class="unit">개월</span></span></label>
        </div>
        ${result.by_ai ? '<p class="field-help">AI가 문장을 읽고 정리한 값이에요.</p>' : ""}
        <p class="ob-error" id="ob-error" role="alert"></p>
      </div>
      <div class="ob-actions"><button class="btn btn-primary btn-lg" type="button" data-ob="goal-ok">확인</button>
        <button class="btn btn-ghost btn-lg" type="button" data-ob="goal-back">다시 적기</button></div>`;
    ($("#goal-amount", card).value ? $("#goal-months", card) : $("#goal-amount", card)).focus();
  }

  function onGoalOk() {
    const amount = Number(digits($("#goal-amount", card).value));
    const months = Number(digits($("#goal-months", card).value));
    if (!amount || amount < 10) { errorEl().textContent = "목표 금액을 10만 원 이상으로 적어 주세요."; return; }
    if (!months || months > 240) { errorEl().textContent = "기간을 1~240개월 사이로 적어 주세요."; return; }
    const text = $("#goal-text", card).value.trim() || `${won(toWon(amount))} 모으기`;
    answers.goal = { goal_text: text.slice(0, 100), goal_amount: toWon(amount), goal_months: months };
    next();
  }

  function display(q) {
    const v = answers[q.key];
    if (q.key === "goal") return v ? `${won(v.goal_amount)}, ${v.goal_months}개월` : "없음";
    if (q.type === "choice") {
      const option = q.options.find(([value]) => value === v);
      return option ? option[1] : "모름";
    }
    if (v === null || v === undefined || v === "") return "모름";
    if (q.type === "amount") return won(toWon(v));
    if (q.key === "age") return `만 ${v}세`;
    return String(v);
  }

  function renderSummary() {
    view = "summary";
    editing = true;
    setProgress();
    const rows = visible().map((q) =>
      `<li><span class="k">${escapeHtml(q.label)}</span><span class="v">${escapeHtml(display(q))}${q.key === "goal" && answers.goal ? `<small>${escapeHtml(answers.goal.goal_text)}</small>` : ""}</span>
        <button type="button" data-edit="${questions.indexOf(q)}" aria-label="${escapeHtml(q.label)} 고치기">고치기</button></li>`
    ).join("");
    card.innerHTML = `<h1 class="ob-title" id="ob-title">이대로 플랜을 만들까요?</h1>
      <p class="ob-help">다른 곳이 있으면 고쳐 주세요. 나중에 내 정보에서도 바꿀 수 있어요.</p>
      <ul class="summary-list ob-body">${rows}</ul>
      <p class="ob-error" id="ob-error" role="alert"></p>
      ${actions(["submit", "플랜 만들기"])}`;
    card.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }

  async function submit(btn) {
    const a = answers;
    const on = (key) => isVisible(byKey(key));
    const amount = (key, fallback = 0) => (on(key) && a[key] !== null && a[key] !== undefined && a[key] !== "" ? toWon(a[key]) : fallback);
    const goal = a.goal || null;
    const payload = {
      age: Number(a.age),
      employment_type: a.employment_type,
      company_size: on("company_size") && a.company_size ? a.company_size : null,
      monthly_income: amount("monthly_income"),
      annual_income: amount("annual_income", null),
      housing_type: a.housing_type,
      rent: amount("rent"),
      fixed_costs: amount("fixed_costs"),
      debt_total: amount("debt_total"),
      debt_monthly: amount("debt_monthly"),
      savings: amount("savings"),
      saving_monthly: amount("saving_monthly"),
      region: a.region || null,
      goal_text: goal ? goal.goal_text : null,
      goal_amount: goal ? goal.goal_amount : null,
      goal_months: goal ? goal.goal_months : null,
    };
    btn.disabled = true;
    btn.textContent = "플랜을 만들고 있어요";
    try {
      const d = await api("/api/onboarding/complete", { method: "POST", body: payload });
      location.href = d.redirect || "/plan";
    } catch (e) {
      errorEl().textContent = e.message;
      btn.disabled = false;
      btn.textContent = "플랜 만들기";
    }
  }

  card.addEventListener("click", (ev) => {
    const choice = ev.target.closest(".choice");
    if (choice) return pick(choice);
    const edit = ev.target.closest("[data-edit]");
    if (edit) return show(Number(edit.dataset.edit));
    const act = ev.target.closest("[data-ob]");
    if (!act) return;
    const handlers = { next: onNext, skip: onSkip, "goal-ok": onGoalOk, "goal-back": () => show(current), submit };
    handlers[act.dataset.ob]?.(act);
  });
  card.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" || ev.isComposing || !ev.target.matches("input")) return;
    ev.preventDefault();
    $("[data-ob]", card)?.click();
  });
  card.addEventListener("input", (ev) => {
    if (ev.target.id === "ob-input") { updateHint(); errorEl().textContent = ""; }
  });
  back.addEventListener("click", prev);

  api("/api/onboarding/questions")
    .then((d) => {
      questions = d.questions;
      answers = d.answers || {};
      show(0);
    })
    .catch((e) => { card.innerHTML = `<p class="ob-error">${escapeHtml(e.message)}</p>`; });
}

/* ------------------------------------------------------------ AI 코치 (SSE 스트리밍) */
const THUMB_UP = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h3z"/><path d="m7 10 4-8a3 3 0 0 1 3 3v4h5.5a2 2 0 0 1 2 2.3l-1.4 8A2 2 0 0 1 18.1 21H7"/></svg>';
const THUMB_DOWN = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 14V3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-3z"/><path d="m17 14-4 8a3 3 0 0 1-3-3v-4H4.5a2 2 0 0 1-2-2.3l1.4-8A2 2 0 0 1 5.9 3H17"/></svg>';

function sourcesHtml(sources) {
  if (!sources || !sources.length) return "";
  const items = sources.map((s) =>
    `<li><a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.name)}</a> <span>${escapeHtml(s.as_of || "")} 기준</span></li>`
  ).join("");
  return `<details class="sources"><summary>출처 ${sources.length}개</summary><ul>${items}</ul></details>`;
}

function metaHtml() {
  return '<div class="msg-meta"><span class="ai-label">AI 답변</span>' +
    `<button class="fb-btn" type="button" data-rating="1" aria-label="도움이 됐어요" title="도움이 됐어요">${THUMB_UP}</button>` +
    `<button class="fb-btn" type="button" data-rating="-1" aria-label="아쉬워요" title="아쉬워요">${THUMB_DOWN}</button></div>`;
}

// Mock responses may arrive together. Reveal them over a few frames without
// delaying the request or replaying saved conversation history.
function createReplyRenderer(body, bubble) {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let characters = [], visible = 0, frame = 0, previousTime = 0, finished = null;

  function render() {
    body.innerHTML = renderMd(characters.slice(0, visible).join(""));
    bubble.scrollIntoView({ behavior: "auto", block: "end" });
  }

  function settle() {
    if (finished) { finished(); finished = null; }
  }

  function flush() {
    cancelAnimationFrame(frame);
    frame = 0;
    previousTime = 0;
    visible = characters.length;
    render();
    settle();
  }

  function tick(now) {
    frame = 0;
    if (motion.matches || document.hidden) { flush(); return; }
    const elapsed = previousTime ? Math.min(now - previousTime, 48) : 16;
    previousTime = now;
    const remaining = characters.length - visible;
    visible += Math.min(remaining, Math.max(1, Math.ceil(remaining * (1 - Math.exp(-elapsed / 85)))));
    render();
    if (visible < characters.length) frame = requestAnimationFrame(tick);
    else { previousTime = 0; settle(); }
  }

  const onMotionChange = () => { if (motion.matches) flush(); };
  const onVisibilityChange = () => { if (document.hidden) flush(); };
  motion.addEventListener("change", onMotionChange);
  document.addEventListener("visibilitychange", onVisibilityChange);

  return {
    write(text, immediate = false) {
      characters = Array.from(text);
      visible = Math.min(visible, characters.length);
      if (immediate || motion.matches || document.hidden) flush();
      else if (!frame) frame = requestAnimationFrame(tick);
    },
    finish() {
      if (motion.matches || document.hidden) flush();
      return visible === characters.length ? Promise.resolve() : new Promise((resolve) => { finished = resolve; });
    },
    dispose() {
      cancelAnimationFrame(frame);
      motion.removeEventListener("change", onMotionChange);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      settle();
    },
  };
}

function addMessage(chat, role, html) {
  const div = document.createElement("div");
  div.className = `msg ${role} is-new`;
  div.innerHTML = html;
  chat.appendChild(div);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  div.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "end" });
  return div;
}

async function streamChat(message, bubble) {
  const status = document.createElement("div");
  status.className = "status-line";
  status.setAttribute("aria-hidden", "true");
  status.textContent = "답을 준비하고 있어요";
  const body = document.createElement("div");
  body.className = "body";
  // Announce the completed answer once instead of every animated fragment.
  bubble.setAttribute("aria-busy", "true");
  bubble.replaceChildren(status, body);
  const renderer = createReplyRenderer(body, bubble);
  let completed = null;

  try {
    const res = await fetch("/api/coach/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      credentials: "same-origin",
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      status.remove();
      renderer.write(data.detail || "답변을 받지 못했어요.", true);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", text = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const raw of events) {
        if (!raw.startsWith("data: ")) continue;
        const ev = JSON.parse(raw.slice(6));
        if (ev.type === "status") {
          status.textContent = ev.text;
          $("#coach-status").textContent = ev.text;
        }
        else if (ev.type === "notice") toast(ev.text);
        else if (ev.type === "delta") { status.remove(); text += ev.text; renderer.write(text); }
        // Safety corrections and errors replace pending text immediately.
        else if (ev.type === "replace") { status.remove(); text = ev.text; renderer.write(text, true); }
        else if (ev.type === "error") {
          status.remove();
          text = (text ? `${text}\n\n` : "") + ev.text;
          renderer.write(text, true);
        }
        else if (ev.type === "done") { status.remove(); completed = ev; }
      }
    }
    await renderer.finish();
    if (completed) {
      bubble.dataset.messageId = completed.message_id;
      bubble.insertAdjacentHTML("beforeend", sourcesHtml(completed.sources) + metaHtml());
      bubble.scrollIntoView({ behavior: "auto", block: "end" });
    }
  } finally {
    renderer.dispose();
    bubble.setAttribute("aria-busy", "false");
  }
}

function initCoach() {
  const chat = $("#chat"), form = $("#chat-form"), input = $("#chat-input"), sendBtn = $(".send-btn", form);
  const dialog = $("#feedback-dialog");
  const coachStatus = $("#coach-status");
  let busy = false;

  const autosize = () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 160)}px`; };

  async function send(text) {
    if (busy || !text) return;
    busy = true;
    sendBtn.disabled = true;
    coachStatus.textContent = "코치가 답변을 준비하고 있어요";
    $("#suggestions")?.remove();
    addMessage(chat, "user", escapeHtml(text));
    const bubble = addMessage(chat, "bot", "");
    try { await streamChat(text, bubble); }
    catch { bubble.innerHTML = `<div class="body">${renderMd("연결이 끊겼어요. 다시 시도해 주세요.")}</div>`; }
    finally {
      busy = false;
      sendBtn.disabled = false;
      coachStatus.textContent = "";
      input.focus();
    }
  }

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    input.value = "";
    autosize();
    send(text);
  });
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); form.requestSubmit(); }
  });
  $$(".suggestion").forEach((b) => b.addEventListener("click", () => send(b.textContent.trim())));

  async function sendFeedback(bubble, btn, comment = null) {
    try {
      await api("/api/feedback", {
        method: "POST",
        body: { message_id: Number(bubble.dataset.messageId), rating: Number(btn.dataset.rating), comment },
      });
      $$(".fb-btn", bubble).forEach((b) => b.classList.toggle("on", b === btn));
      toast("의견 고마워요. 답변을 고치는 데 쓸게요.");
    } catch (e) { toast(e.message); }
  }

  chat.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".fb-btn");
    if (!btn) return;
    const bubble = btn.closest(".msg");
    if (!Number(bubble.dataset.messageId)) return;
    if (Number(btn.dataset.rating) > 0 || !dialog?.showModal) { sendFeedback(bubble, btn); return; }
    const comment = $("textarea", dialog);
    comment.value = "";
    dialog.returnValue = "";
    dialog.onclose = () => {
      if (dialog.returnValue === "send") sendFeedback(bubble, btn, comment.value.trim() || null);
    };
    dialog.showModal();
  });

  const preset = new URLSearchParams(location.search).get("q");
  if (preset) { history.replaceState(null, "", "/coach"); send(preset); }
  else chat.lastElementChild?.scrollIntoView({ block: "end" });
}

/* ------------------------------------------------------------ 플랜: 적금 계산 */
function initPlan() {
  const form = $("#simulate-form"), out = $("#simulate-result");
  if (!form) return;
  const monthsField = $("#sim-months-field"), help = $("#sim-help");

  function syncProduct() {
    const youth = form.elements.product.value === "youth_future_savings";
    monthsField.hidden = youth;
    help.textContent = youth
      ? "3년 납입, 월 50만 원까지 계산해요. 기여금 유형은 내 연봉과 회사 규모로 정해요."
      : "연 3.5% 단리, 이자소득세 15.4%를 가정해요.";
  }

  form.addEventListener("change", syncProduct);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const product = form.elements.product.value;
    const monthly = Number(digits(form.elements.monthly_amount.value));
    if (!monthly) { out.innerHTML = '<p class="ob-error">매달 넣을 돈을 적어 주세요.</p>'; return; }
    const body = { monthly_amount: toWon(monthly), product };
    if (product === "general") body.months = Number(digits(form.elements.months.value)) || 12;
    try {
      const d = await api("/api/goals/simulate", { method: "POST", body });
      const r = d.readable;
      const rows = [["원금", r["원금"]], ["이자(세전)", r["세전 이자"]], ["세금", r["세금"]]];
      if (d.contribution) rows.push(["정부기여금", r["정부기여금"]]);
      out.innerHTML = `<p class="label">${d.months}개월 뒤 받는 돈</p><p class="sim-total">${escapeHtml(r["만기 수령액"])}</p>
        <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join("")}</dl>
        <p class="card-foot">${renderMd(d.notes.join(" "))}</p>`;
    } catch (e) { out.innerHTML = `<p class="ob-error">${escapeHtml(e.message)}</p>`; }
  });
  syncProduct();
}

async function regenerate() {
  try { await api("/api/plans/generate", { method: "POST" }); location.reload(); }
  catch (e) { toast(e.message); }
}

/* ------------------------------------------------------------ 내 정보 */
function initSettings() {
  const form = $("#profile-form");
  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {};
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.matches("[data-manwon]")) {
        const v = digits(el.value);
        if (v) body[el.name] = toWon(v);
        else if (el.name === "annual_income") body[el.name] = null;
      } else if (el.name === "age") {
        if (digits(el.value)) body.age = Number(digits(el.value));
      } else {
        body[el.name] = el.value || null;
      }
    }
    const btn = $('button[type="submit"]', form);
    btn.disabled = true;
    try { await api("/api/profile", { method: "PUT", body }); toast("저장했어요. 플랜도 다시 계산했어요."); }
    catch (e) { toast(e.message); }
    btn.disabled = false;
  });

  $("#memory-list")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest('[data-action="delete-memory"]');
    if (!btn) return;
    const li = btn.closest("li"), list = li.parentElement;
    try {
      await api(`/api/memories/${li.dataset.memoryId}`, { method: "DELETE" });
      li.remove();
      if (!list.children.length) list.innerHTML = '<li class="empty">아직 기억한 내용이 없어요.</li>';
      toast("지웠어요.");
    } catch (e) { toast(e.message); }
  });
}

async function deleteAccount() {
  try { const d = await api("/api/account", { method: "DELETE" }); location.href = d.redirect || "/"; }
  catch (e) { toast(e.message); }
}

/* ------------------------------------------------------------ 약관 동의 */
function initConsent() {
  const all = $("#consent-all"), items = $$("[data-consent]");
  if (!all) return;
  const sync = () => { all.checked = items.every((i) => i.checked); };
  all.addEventListener("change", () => items.forEach((i) => { i.checked = all.checked; }));
  items.forEach((i) => i.addEventListener("change", sync));
  sync();
}

document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  if (el.dataset.action === "regenerate") regenerate();
  if (el.dataset.action === "delete-account") {
    const dialog = $("#delete-dialog");
    if (!dialog?.showModal) { if (confirm("탈퇴할까요? 모든 정보가 바로 지워지고 되돌릴 수 없어요.")) deleteAccount(); return; }
    dialog.returnValue = "";
    dialog.onclose = () => { if (dialog.returnValue === "delete") deleteAccount(); };
    dialog.showModal();
  }
});

const page = document.body.dataset.page;
if (page === "landing") initLanding();
if (page === "onboarding") initOnboarding();
if (page === "coach") initCoach();
if (page === "plan") initPlan();
if (page === "settings") initSettings();
if (page === "consent") initConsent();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
