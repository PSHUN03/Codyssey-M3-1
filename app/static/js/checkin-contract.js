/* BE-04 request preparation only. Response/progress contracts are still pending (#14, #22). */
(() => {
  "use strict";
  const MAX_AMOUNT = 10_000_000_000;
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
    return { url: `/api/checkins/${week}`, method: "PUT", body: { paid } };
  }
  function savingsRequest(month, amount) {
    if (!validMonth(month)) throw new TypeError("월은 YYYY-MM 형식이어야 해요.");
    if (!Number.isSafeInteger(amount) || amount < 0 || amount > MAX_AMOUNT) throw new RangeError("저축 금액은 원 단위의 유효한 정수여야 해요.");
    return { url: `/api/savings/${month}`, method: "PUT", body: { amount } };
  }
  const contract = { weeklyRequest, savingsRequest, validWeek, validMonth };
  if (typeof module !== "undefined" && module.exports) module.exports = contract;
  else globalThis.SadariCheckinContract = contract;
})();
