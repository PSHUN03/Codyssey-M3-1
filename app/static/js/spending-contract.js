/* DATA-06 preview contract (#15/#56). Upload only after an explicit preview action. */
(() => {
  "use strict";
  const CATEGORIES = Object.freeze(["식비", "교통", "쇼핑", "주거", "의료", "교육", "통신", "문화", "기타", "수입"]);
  const MAPPING_KEYS = ["date", "merchant", "withdrawal", "deposit", "amount", "direction"];
  const MAX_BYTES = 2 * 1024 * 1024, MAX_ROWS = 10_000;
  const isObject = value => value && typeof value === "object" && !Array.isArray(value);
  function validDate(value) {
    if (typeof value !== "string" || !/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(value + "T00:00:00Z");
    return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }
  function safeSum(values) {
    const total = values.reduce((sum, value) => sum + value, 0);
    if (!Number.isSafeInteger(total)) throw new RangeError("금액 합계가 표시 가능한 범위를 초과했어요.");
    return total;
  }
  function mappingFields(mapping, headerRow) {
    if (!isObject(mapping) || !Object.keys(mapping).length) throw new TypeError("열 선택 형식을 확인해 주세요.");
    if (!Number.isInteger(headerRow) || headerRow < 0 || headerRow >= 20) throw new TypeError("제목 행은 0~19 범위여야 해요.");
    for (const [key, value] of Object.entries(mapping)) {
      if (!MAPPING_KEYS.includes(key) || !Number.isInteger(value) || value < 0 || value >= 100) throw new TypeError("열 번호는 0부터 시작하는 정수여야 해요.");
    }
    if (!("date" in mapping) || !("merchant" in mapping) || !["amount", "withdrawal", "deposit"].some(key => key in mapping)) throw new TypeError("거래일·거래처와 금액 열을 선택해 주세요.");
    if (new Set(Object.values(mapping)).size !== Object.keys(mapping).length) throw new TypeError("같은 열을 중복해서 선택하지 말아 주세요.");
    return { mapping: { ...mapping }, headerRow };
  }
  function buildPreviewRequest(file, options = {}) {
    if (!file || !/\.(csv|xlsx)$/i.test(file.name || "") || !file.size || file.size > MAX_BYTES) throw new TypeError("2MB 이하의 CSV·XLSX 파일을 선택해 주세요.");
    const body = new FormData();
    body.append("file", file, file.name);
    if (options.mapping != null || options.headerRow != null) {
      const fields = mappingFields(options.mapping, options.headerRow);
      body.append("mapping", JSON.stringify(fields.mapping));
      body.append("header_row", String(fields.headerRow));
    }
    return { url: "/api/transactions/preview", method: "POST", credentials: "same-origin", body, ...(options.signal ? { signal: options.signal } : {}) };
  }
  function normalizePreview(payload) {
    if (!isObject(payload) || typeof payload.needs_mapping !== "boolean" || !Array.isArray(payload.transactions) || !Array.isArray(payload.errors)) throw new TypeError("미리보기 응답 형식을 확인해 주세요.");
    if (payload.transactions.length > MAX_ROWS) throw new RangeError("미리보기는 10,000건까지 처리할 수 있어요.");
    const errors = payload.errors.map(error => {
      if (!isObject(error) || !Number.isInteger(error.row) || error.row < 1 || typeof error.reason !== "string") throw new TypeError("행 오류 응답 형식을 확인해 주세요.");
      return { row: error.row, reason: error.reason.slice(0, 2000) };
    });
    if (payload.needs_mapping) {
      if (payload.transactions.length || !Array.isArray(payload.preview) || payload.preview.length > 20 || payload.preview.some(row => !Array.isArray(row) || row.length > 100 || row.some(cell => typeof cell !== "string"))) throw new TypeError("열 선택 미리보기 형식을 확인해 주세요.");
      return { status: "mapping-required", preview: payload.preview.map(row => row.map(cell => cell.slice(0, 2000))), transactions: [], expenses: [], errors, needsConfirmation: true };
    }
    const transactions = payload.transactions.map((row, previewIndex) => {
      if (!isObject(row) || !validDate(row.date) || !Number.isSafeInteger(row.amount) || typeof row.merchant !== "string" || !CATEGORIES.includes(row.category)) throw new TypeError("변환된 거래 형식을 확인해 주세요.");
      // previewIndex is a local display key, never a saved transaction ID.
      return { previewIndex, date: row.date, merchant: row.merchant.slice(0, 2000), amount: row.amount, category: row.category };
    });
    const expenses = transactions.filter(row => row.amount < 0).map(row => ({ ...row, signedAmount: row.amount, amount: -row.amount, fixed: null }));
    const fields = mappingFields(payload.mapping, payload.header_row);
    return { status: errors.length ? "partial" : transactions.length ? "ready" : "empty",
      transactions, expenses, errors, mapping: fields.mapping, headerRow: fields.headerRow,
      totalSpending: safeSum(expenses.map(row => row.amount)),
      totalDeposits: safeSum(transactions.filter(row => row.amount > 0).map(row => row.amount)),
      fixedTotal: null, variableTotal: null, needsConfirmation: errors.length > 0 };
  }
  function createPreviewClient(transport) {
    // Requiring explicit injection prevents an import or sample action from uploading a file.
    if (typeof transport !== "function") throw new TypeError("미리보기 전송 함수를 명시해야 해요.");
    return async (file, options) => {
      const request = buildPreviewRequest(file, options);
      const { url, ...init } = request;
      const response = await transport(url, init);
      if (!response.ok) {
        const messages = { 401: "로그인이 필요해요.", 403: "필수 동의를 확인해 주세요.", 404: "미리보기 기능이 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.", 409: "재무 진단을 먼저 마쳐 주세요.", 413: "2MB 이하의 파일을 선택해 주세요.", 422: "파일 크기·형식 또는 열 선택을 확인해 주세요." };
        const error = new Error(messages[response.status] || "미리보기를 불러오지 못했어요. 다시 시도해 주세요.");
        error.status = response.status;
        throw error;
      }
      let payload;
      try { payload = await response.json(); }
      catch { throw new Error("미리보기 응답을 읽지 못했어요. 잠시 후 다시 시도해 주세요."); }
      return normalizePreview(payload);
    };
  }
  function createSampleSource(config) {
    const rows = config.rows.map(row => ({ ...row })), categories = [...config.categories];
    return { read: () => ({ rows: rows.map(row => ({ ...row })), categories: [...categories] }) };
  }
  const contract = { CATEGORIES, MAX_BYTES, MAX_ROWS, buildPreviewRequest, normalizePreview, createPreviewClient, createSampleSource };
  if (typeof module !== "undefined" && module.exports) module.exports = contract;
  else globalThis.SadariSpendingContract = contract;
})();
