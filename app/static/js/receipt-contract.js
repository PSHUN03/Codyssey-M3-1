/* AI-02 response fields agreed in #18. No upload or save endpoint is enabled here. */
(() => {
  "use strict";
  function fromScanResponse(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new TypeError("영수증 응답 형식을 확인해 주세요.");
    if (payload.currency != null && payload.currency !== "KRW") throw new TypeError("원화 영수증인지 확인해 주세요.");
    return {
      date: typeof payload.date === "string" ? payload.date : null,
      merchant: typeof payload.merchant_name === "string" ? payload.merchant_name : null,
      amount: Number.isSafeInteger(payload.total_amount) && payload.total_amount > 0 ? payload.total_amount : null,
    };
  }
  const contract = { fromScanResponse };
  if (typeof module !== "undefined" && module.exports) module.exports = contract;
  else globalThis.SadariReceiptContract = contract;
})();
