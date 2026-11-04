/* FE-01: explicit sample adapter only. No financial API calls or database writes. */
(() => {
  "use strict";
  const contract = typeof module !== "undefined" && module.exports
    ? require("./checkin-contract.js") : globalThis.SadariCheckinContract;

  const MAX_AMOUNT = 10_000_000_000;
  const validAmount = value => Number.isSafeInteger(value) && value >= 0 && value <= MAX_AMOUNT;
  const clone = value => JSON.parse(JSON.stringify(value));

  function parseMan(value) {
    const text = String(value).trim();
    if (!/^\d+$/.test(text) || !validAmount(Number(text) * 10000)) {
      throw new Error("0~1,000,000만 원 사이의 정수 금액을 입력해 주세요.");
    }
    return Number(text) * 10000;
  }

  function summarize(records, goalAmount) {
    const total = records.reduce((sum, record) => sum + record.amount, 0);
    const percent = goalAmount > 0 ? total / goalAmount * 100 : 0;
    return { total, percent, cappedPercent: Math.min(100, percent), remaining: Math.max(0, goalAmount - total) };
  }

  function createSampleStore(config, storage) {
    const key = `sadari:fe01:sample:v1:${encodeURIComponent(config.scope)}:${config.month}`;
    const seed = () => ({ version: 1, week: config.week, paid: null, records: clone(config.records) });
    let persistent = !!storage;
    let state;
    function load() {
      const next = seed();
      try {
        const saved = JSON.parse(storage?.getItem(key) || "null");
        if (saved?.version === 1) {
          if (saved.week === config.week && typeof saved.paid === "boolean") next.paid = saved.paid;
          if (Array.isArray(saved.records)) {
            next.records.forEach(record => {
              const match = saved.records.find(item => item?.month === record.month && validAmount(item.amount));
              if (match) record.amount = match.amount;
            });
          }
        }
      } catch { persistent = false; }
      state = next;
    }
    load();
    function persist() {
      try { if (storage) { storage.setItem(key, JSON.stringify(state)); persistent = true; } }
      catch { persistent = false; }
    }
    return {
      read: () => clone(state),
      reload() { load(); return clone(state); },
      isPersistent: () => persistent,
      recordWeekly(paid) {
        const request = contract.weeklyRequest(config.week, paid);
        state.paid = request.body.paid;
        persist();
        return clone(state);
      },
      recordSavings(amount) {
        if (!validAmount(amount)) throw new RangeError("Invalid sample savings amount.");
        const record = state.records.find(item => item.month === config.month);
        if (!record) throw new Error("Current sample month is missing.");
        record.amount = amount;
        persist();
        return clone(state);
      },
    };
  }

  function createChart(container, sample = true) {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const ns = "http://www.w3.org/2000/svg";
    const format = value => new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 4 }).format(value);
    let records = [], width = 0, signature = "", seen = false, armed = false, raf = 0, targets = [];
    const make = (tag, attributes, text) => {
      const node = document.createElementNS(ns, tag);
      Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
      if (text !== undefined) node.textContent = text;
      return node;
    };
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function finish() {
      stop();
      targets.forEach(target => {
        target.bar.setAttribute("y", target.y);
        target.bar.setAttribute("height", target.height);
        target.bar.dataset.animationProgress = "1";
        target.label.setAttribute("y", target.labelY);
        target.label.style.opacity = "1";
      });
      container.dataset.animation = motion.matches ? "reduced" : "complete";
    }
    function animate() {
      stop();
      if (motion.matches) { finish(); return; }
      const current = targets;
      const starts = current.map(target => ({ height: Number(target.bar.getAttribute("height")), labelY: Number(target.label.getAttribute("y")), opacity: Number(target.label.style.opacity || 1) }));
      const started = performance.now();
      container.dataset.animation = "running";
      container.dataset.sequence = "left-to-right";
      function tick(now) {
        let done = true;
        current.forEach((target, index) => {
          const progress = Math.min(1, Math.max(0, (now - started - index * 85) / 680));
          const eased = 1 - (1 - progress) ** 3;
          const height = starts[index].height + (target.height - starts[index].height) * eased;
          target.bar.setAttribute("height", height);
          target.bar.setAttribute("y", target.baseline - height);
          target.bar.dataset.animationProgress = progress.toFixed(3);
          target.label.setAttribute("y", starts[index].labelY + (target.labelY - starts[index].labelY) * eased);
          target.label.style.opacity = starts[index].opacity + (1 - starts[index].opacity) * eased;
          if (progress < 1) done = false;
        });
        if (done) { raf = 0; finish(); } else raf = requestAnimationFrame(tick);
      }
      raf = requestAnimationFrame(tick);
    }
    const observer = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
      if (!seen && entries.some(entry => entry.isIntersecting)) {
        seen = true; armed = false; observer.unobserve(container); animate();
      }
    }, { threshold: .18 }) : null;
    function draw() {
      const nextWidth = Math.floor(container.getBoundingClientRect().width);
      if (!records.length) { stop(); targets = []; signature = ""; container.replaceChildren(); return; }
      if (nextWidth < 100) return;
      const nextSignature = JSON.stringify(records);
      if (nextWidth === width && nextSignature === signature && (seen || armed)) return;
      const changed = nextSignature !== signature;
      const previous = targets.map(target => ({ height: Number(target.bar.getAttribute("height")), labelY: Number(target.label.getAttribute("y")) }));
      stop();
      const values = records.map(record => record.amount / 10000);
      const upper = Math.max(20, Math.ceil(Math.max(...values) * 1.2 / 20) * 20);
      const left = Math.max(64, Math.min(88, format(upper).length * 7 + 14));
      const height = 240, top = 30, bottom = 38, right = 12;
      const plotWidth = nextWidth - left - right, plotHeight = height - top - bottom;
      const svg = make("svg", { viewBox: `0 0 ${nextWidth} ${height}`, role: "img", "aria-label": `월별 ${sample ? "샘플 " : ""}저축: ${records.map(record => `${record.month} ${format(record.amount / 10000)}만 원`).join(", ")}` });
      svg.append(make("title", {}, sample ? "월별 저축 추이 — 샘플 데이터" : "월별 저축 기록"));
      for (let i = 0; i <= 4; i++) {
        const y = top + plotHeight - plotHeight * i / 4;
        svg.append(make("line", { x1: left, y1: y, x2: nextWidth - right, y2: y, stroke: "var(--hairline)", "stroke-width": 1 }));
        svg.append(make("text", { x: left - 8, y: y + 4, "text-anchor": "end" }, format(upper * i / 4)));
      }
      const step = plotWidth / values.length, barWidth = Math.min(42, step * .52), nextTargets = [];
      values.forEach((amount, index) => {
        const x = left + step * (index + .5), barHeight = amount / upper * plotHeight;
        const y = top + plotHeight - barHeight, labelY = Math.max(16, y - 8);
        const bar = make("rect", { x: x - barWidth / 2, y, width: barWidth, height: barHeight, rx: 4, fill: index === values.length - 1 ? "var(--lime)" : "var(--lime-neutral)", "data-fe01-bar": index });
        const valueLabel = amount >= 10000 ? `${format(Math.round(amount / 10000 * 10) / 10)}억` : format(amount);
        const label = make("text", { x, y: labelY, "text-anchor": "middle", class: "fe01-chart-value" }, valueLabel);
        svg.append(bar, label);
        if (nextWidth >= 330 || (!sample && values.length <= 6) || [0, 2, values.length - 1].includes(index)) {
          svg.append(make("text", { x, y: height - 12, "text-anchor": "middle" }, `${Number(records[index].month.slice(5))}월`));
        }
        nextTargets.push({ bar, label, y, height: barHeight, labelY, baseline: top + plotHeight });
      });
      container.replaceChildren(svg);
      targets = nextTargets; width = nextWidth; signature = nextSignature;
      if (motion.matches || !observer) { seen = true; armed = false; finish(); }
      else if (!seen) {
        targets.forEach(target => {
          target.bar.setAttribute("height", "0"); target.bar.setAttribute("y", target.baseline); target.bar.dataset.animationProgress = "0";
          target.label.setAttribute("y", target.baseline - 8); target.label.style.opacity = "0";
        });
        armed = true; container.dataset.animation = "waiting"; observer.unobserve(container); observer.observe(container);
      } else if (changed && previous.length === targets.length) {
        targets.forEach((target, index) => {
          target.bar.setAttribute("height", previous[index].height); target.bar.setAttribute("y", target.baseline - previous[index].height); target.label.setAttribute("y", previous[index].labelY);
        });
        animate();
      } else finish();
    }
    motion.addEventListener("change", () => { if (motion.matches) { seen = true; armed = false; observer?.unobserve(container); finish(); } });
    if ("ResizeObserver" in window) new ResizeObserver(draw).observe(container);
    else window.addEventListener("resize", draw);
    return { render(nextRecords) { records = nextRecords; draw(); } };
  }

  function init() {
    const root = document.querySelector("[data-fe01]");
    const source = document.getElementById("fe01-sample-config");
    if (!root || !source) return;
    let config;
    try { config = JSON.parse(source.textContent); } catch { return; }
    if (config.mode !== "sample") return;
    let storage;
    try { storage = window.sessionStorage; } catch { storage = null; }
    const store = createSampleStore(config, storage);
    const format = value => new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 4 }).format(value);
    const won = amount => `${format(amount / 10000)}만 원`;
    const monthLabel = month => `${month.slice(0, 4)}년 ${Number(month.slice(5))}월`;
    const input = root.querySelector("#fe01-amount");
    const form = root.querySelector("[data-fe01-month-form]");
    const chartNode = root.querySelector("[data-fe01-chart]");
    const chart = chartNode ? createChart(chartNode) : null;
    const setText = (selector, text) => { const element = root.querySelector(selector); if (element) element.textContent = text; };
    function render() {
      const state = store.read();
      const current = state.records.find(record => record.month === config.month).amount;
      root.querySelectorAll("[data-fe01-weekly]").forEach(button => button.setAttribute("aria-pressed", String(state.paid === (button.dataset.fe01Weekly === "paid"))));
      setText("[data-fe01-week-status]", state.paid === true ? "이번 주 저축 여부를 샘플에 기록했어요." : state.paid === false ? "괜찮아요. 다음 계획을 코치와 함께 정해봐요." : "이번 주 저축 여부를 알려 주세요.");
      const coach = root.querySelector("[data-fe01-coach]");
      if (coach) coach.hidden = state.paid !== false;
      setText("[data-fe01-month-status]", `${config.month_label} 샘플 기록: ${won(current)}`);
      const summary = summarize(state.records, config.goal.amount);
      setText("[data-fe01-total]", won(summary.total));
      setText("[data-fe01-current]", won(current));
      setText("[data-fe01-percent]", `${summary.percent.toFixed(1)}% 달성`);
      setText("[data-fe01-remaining]", summary.remaining ? `목표까지 ${won(summary.remaining)}` : "샘플 목표 금액을 모았어요");
      const progress = root.querySelector("[data-fe01-progress]");
      if (progress) {
        progress.setAttribute("aria-valuenow", String(Math.round(summary.cappedPercent * 10) / 10));
        progress.setAttribute("aria-valuetext", `${won(summary.total)}, 샘플 목표의 ${summary.percent.toFixed(1)}%`);
        root.querySelector("[data-fe01-fill]").style.width = `${summary.cappedPercent}%`;
      }
      const previous = state.records.at(-2).amount, difference = current - previous;
      setText("[data-fe01-comparison]", difference > 0 ? `지난달보다 ${won(difference)} 더 모았어요` : difference < 0 ? `지난달보다 ${won(-difference)} 적게 모았어요` : "지난달과 같은 금액이에요");
      const list = root.querySelector("[data-fe01-records]");
      if (list) {
        list.replaceChildren();
        [...state.records].reverse().forEach(record => {
          const row = document.createElement("div"); row.className = "fe01-record";
          const label = document.createElement("span"); label.textContent = monthLabel(record.month);
          const amount = document.createElement("strong"); amount.textContent = won(record.amount);
          row.append(label, amount); list.append(row);
        });
      }
      chart?.render(state.records);
    }
    if (input) input.value = String(store.read().records.find(record => record.month === config.month).amount / 10000);
    root.querySelectorAll("[data-fe01-weekly]").forEach(button => button.addEventListener("click", () => { store.recordWeekly(button.dataset.fe01Weekly === "paid"); render(); }));
    form?.addEventListener("submit", event => {
      event.preventDefault();
      const error = root.querySelector("#fe01-amount-error");
      try {
        const amount = parseMan(input.value);
        store.recordSavings(amount);
        input.removeAttribute("aria-invalid"); error.hidden = true; render();
        setText("[data-fe01-month-status]", store.isPersistent() ? "입력한 금액을 샘플 기록에 반영했어요. 실제 저축 내역은 변경하지 않아요." : "샘플에 반영했어요. 이 브라우저에서는 새로고침하면 초기화될 수 있어요.");
      } catch (exception) {
        error.textContent = input.value === "" ? "저축 금액을 입력해 주세요." : exception.message;
        error.hidden = false; input.setAttribute("aria-invalid", "true"); input.focus();
      }
    });
    input?.addEventListener("input", event => {
      // This field validates the full value; the legacy numeric filter strips signs and decimals.
      event.stopPropagation();
      try { parseMan(input.value); input.removeAttribute("aria-invalid"); root.querySelector("#fe01-amount-error").hidden = true; } catch { /* Keep the inline error until the value is valid. */ }
    });
    window.addEventListener("pageshow", event => {
      if (!event.persisted) return;
      store.reload(); render();
      if (input) input.value = String(store.read().records.find(record => record.month === config.month).amount / 10000);
    });
    render();
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { parseMan, summarize, createSampleStore };
  if (typeof window !== "undefined") window.SadariFe01Chart = createChart;
  if (typeof document !== "undefined") init();
})();
