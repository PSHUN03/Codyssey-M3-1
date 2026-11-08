/* BE-04 #62 read/write adapter. GET /api/savings also returns cumulative goal progress. */
(() => {
  "use strict";
  const MAX_AMOUNT = 10_000_000;
  const isObject = value => value && typeof value === "object" && !Array.isArray(value);
  const validAmount = value => Number.isSafeInteger(value) && value >= 0 && value <= MAX_AMOUNT;
  function validMonth(month) {
    return typeof month === "string" && /^(?!0000)\d{4}-(0[1-9]|1[0-2])$/.test(month);
  }
  function validWeek(week) {
    if (typeof week !== "string" || !/^(?!0000)\d{4}-W\d{2}$/.test(week)) return false;
    const year = Number(week.slice(0, 4)), number = Number(week.slice(6));
    const weekday = new Date(`${week.slice(0, 4)}-01-01T00:00:00Z`).getUTCDay();
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const maximum = weekday === 4 || (weekday === 3 && leap) ? 53 : 52;
    return number >= 1 && number <= maximum;
  }
  function weeklyRequest(week, paid) {
    if (!validWeek(week)) throw new TypeError("주차는 유효한 YYYY-Www 형식이어야 해요.");
    if (typeof paid !== "boolean") throw new TypeError("납입 여부는 true 또는 false여야 해요.");
    return { url: "/api/savings/weekly-check", method: "PUT", body: { week, paid } };
  }
  function savingsRequest(month, amount) {
    if (!validMonth(month)) throw new TypeError("월은 YYYY-MM 형식이어야 해요.");
    if (!Number.isSafeInteger(amount) || amount < 0 || amount > MAX_AMOUNT) throw new RangeError("저축 금액은 원 단위의 유효한 정수여야 해요.");
    return { url: "/api/savings/monthly", method: "POST", body: { month, amount } };
  }
  function parseMan(value) {
    const text = String(value).trim();
    if (!/^\d+(?:\.\d{1,4})?$/.test(text)) throw new TypeError("0~1,000만 원 사이의 금액을 입력해 주세요. 소수점은 4자리까지 가능해요.");
    const [whole, fraction = ""] = text.split(".");
    const amount = Number(whole) * 10000 + Number(fraction.padEnd(4, "0"));
    if (!validAmount(amount)) throw new RangeError("0~1,000만 원 사이의 금액을 입력해 주세요.");
    return amount;
  }
  function normalizeCheckins(payload) {
    if (!isObject(payload) || !Array.isArray(payload.checkins) || payload.checkins.length > 10000) throw new TypeError("주간 기록 응답을 확인하지 못했어요.");
    const seen = new Set();
    return payload.checkins.map(row => {
      if (!isObject(row) || !validWeek(row.week) || seen.has(row.week)) throw new TypeError("주간 기록 응답을 확인하지 못했어요.");
      // #62 currently reads deposited and writes paid; accept either without losing false.
      const paid = row.paid ?? row.deposited;
      if (typeof paid !== "boolean" || ("paid" in row && "deposited" in row && row.paid !== row.deposited)) throw new TypeError("주간 기록 응답을 확인하지 못했어요.");
      seen.add(row.week); return { week: row.week, paid };
    }).sort((a, b) => b.week.localeCompare(a.week));
  }
  function normalizeSavings(payload) {
    if (!isObject(payload) || !Array.isArray(payload.savings) || payload.savings.length > 10000) throw new TypeError("월별 기록 응답을 확인하지 못했어요.");
    const seen = new Set();
    return payload.savings.map(row => {
      if (!isObject(row) || !validMonth(row.month) || !validAmount(row.amount) || seen.has(row.month)) throw new TypeError("월별 기록 응답을 확인하지 못했어요.");
      seen.add(row.month); return { month: row.month, amount: row.amount };
    }).sort((a, b) => a.month.localeCompare(b.month));
  }
  function normalizeProgress(payload) {
    const progress = isObject(payload) ? payload.progress : null;
    if (!isObject(progress)) return null;
    const { saved_amount: saved, target_amount: target, percentage } = progress;
    if (!Number.isSafeInteger(saved) || saved < 0) return null;
    if (target !== null && (!Number.isSafeInteger(target) || target <= 0)) return null;
    if (percentage !== null && (typeof percentage !== "number" || !Number.isFinite(percentage) || percentage < 0 || percentage > 100)) return null;
    if ((target === null) !== (percentage === null)) return null;
    return { saved, target, percentage };
  }
  function recentRecords(records, month) {
    if (!validMonth(month)) throw new TypeError("기준 월을 확인해 주세요.");
    const index = value => Number(value.slice(0, 4)) * 12 + Number(value.slice(5)) - 1;
    const end = index(month);
    return records.filter(row => index(row.month) >= end - 11 && index(row.month) <= end);
  }
  function createClient(transport) {
    if (typeof transport !== "function") throw new TypeError("전송 함수를 지정해 주세요.");
    async function request(spec, options = {}) {
      const { url, method, body } = spec;
      const response = await transport(url, { method, credentials: "same-origin", cache: "no-store", signal: options.signal,
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
      if (!response.ok) {
        const messages = { 401: "로그인이 필요해요.", 403: "필수 동의를 확인해 주세요.", 404: "저축 기록 기능이 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.", 409: "재무 진단을 먼저 마쳐 주세요.", 422: "주차·월 또는 금액을 확인해 주세요." };
        const error = new Error(messages[response.status] || "서버에서 기록을 확인하지 못했어요. 잠시 후 다시 시도해 주세요.");
        error.status = response.status; throw error;
      }
      try { return await response.json(); }
      catch { throw new Error("서버 응답을 읽지 못했어요. 기록을 다시 불러와 확인해 주세요."); }
    }
    return {
      async loadWeekly(options) { return normalizeCheckins(await request({ url: "/api/checkins", method: "GET" }, options)); },
      async loadSavings(options) { return normalizeSavings(await request({ url: "/api/savings", method: "GET" }, options)); },
      async loadSavingsWithProgress(options) {
        const payload = await request({ url: "/api/savings", method: "GET" }, options);
        return { records: normalizeSavings(payload), progress: normalizeProgress(payload) };
      },
      async saveWeekly(week, paid, options) {
        const payload = await request(weeklyRequest(week, paid), options);
        if (!isObject(payload) || payload.ok !== true || payload.week !== week || payload.paid !== paid) throw new Error("저장 결과를 확인하지 못했어요. 기록을 다시 불러와 확인해 주세요.");
        return { week: payload.week, paid: payload.paid };
      },
      async saveSavings(month, amount, options) {
        const payload = await request(savingsRequest(month, amount), options);
        if (!isObject(payload) || payload.ok !== true || payload.month !== month || payload.amount !== amount) throw new Error("저장 결과를 확인하지 못했어요. 기록을 다시 불러와 확인해 주세요.");
        return { month: payload.month, amount: payload.amount };
      },
    };
  }
  const contract = { weeklyRequest, savingsRequest, validWeek, validMonth, parseMan, normalizeCheckins, normalizeSavings, normalizeProgress, recentRecords, createClient, MAX_AMOUNT };
  if (typeof module !== "undefined" && module.exports) module.exports = contract;
  else globalThis.SadariCheckinContract = contract;
})();
