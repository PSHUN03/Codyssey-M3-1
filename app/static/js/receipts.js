/* FE-05: 샘플 미리보기와 AI-02 영수증 인식(POST /api/receipts/scan). 사진과 결과는 서버에 저장하지 않는다. */
(() => {
  "use strict";
  const contract = typeof module !== "undefined" && module.exports
    ? require("./receipt-contract.js") : globalThis.SadariReceiptContract;
  const MAX_FILE_BYTES = 5 * 1024 * 1024;

  function validateFile(file) {
    if (!file || !["image/jpeg", "image/png"].includes(file.type)) throw new Error("JPG 또는 PNG 사진을 선택해 주세요.");
    if (!file.size) throw new Error("빈 파일은 열 수 없어요. 다른 사진을 선택해 주세요.");
    if (file.size > MAX_FILE_BYTES) throw new Error("5MB 이하의 사진을 선택해 주세요.");
  }

  function parseWon(value) {
    const text = String(value ?? "").trim();
    if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(text)) throw new Error("금액은 1원 이상의 정수로 입력해 주세요.");
    const amount = Number(text.replaceAll(",", ""));
    if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error("금액은 1원 이상의 정수로 입력해 주세요.");
    return amount;
  }

  function validDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(value + "T00:00:00Z");
    return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }

  function validateDraft(draft) {
    const date = String(draft.date ?? "").trim(), merchant = String(draft.merchant ?? "").trim();
    const errors = {};
    if (!validDate(date)) errors.date = "결제 날짜를 확인해 주세요.";
    if (!merchant || merchant.length > 80) errors.merchant = "가맹점 이름을 1~80자로 입력해 주세요.";
    let amount;
    try { amount = parseWon(draft.amount); } catch (error) { errors.amount = error.message; }
    return Object.keys(errors).length ? { errors, record: null } : { errors, record: { date, merchant, amount } };
  }

  function sampleResult(config) {
    return contract.fromScanResponse({ date: config.sample_date, merchant_name: "사다리 커피",
      total_amount: config.example === "missing" ? null : 15500, currency: "KRW" });
  }

  function toDraft(result) {
    return { date: validDate(String(result.date ?? "")) ? result.date : "",
      merchant: typeof result.merchant === "string" ? result.merchant.slice(0, 80) : "",
      amount: Number.isSafeInteger(result.amount) && result.amount > 0 ? String(result.amount) : "" };
  }

  function init() {
    const root = document.getElementById("receipt-page");
    const configElement = document.getElementById("receipt-preview-config");
    if (!root || !configElement) return;
    let config;
    try { config = JSON.parse(configElement.textContent); } catch { return; }
    if (config.mode !== "sample") return;
    const find = selector => root.querySelector(selector);
    const form = find("[data-receipt-form]");
    const fields = { date: form.elements.date, merchant: form.elements.merchant, amount: form.elements.amount };
    const photo = find("[data-local-photo]");
    let stage = "review", source = "sample", objectUrl = null, fileName = "", generation = 0, timer = null;
    let result = sampleResult(config), values = toDraft(result), saved = null, selectedFile = null, recognized = false;

    function clearErrors() {
      Object.entries(fields).forEach(([name, input]) => { input.removeAttribute("aria-invalid"); find(`[data-error="${name}"]`).hidden = true; });
      find("[data-file-error]").hidden = true;
    }
    function releasePhoto() {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null; fileName = ""; photo.removeAttribute("src");
    }
    function announce(text) { find("[data-live]").textContent = text; }
    function render(syncFields = false) {
      const review = stage === "review", complete = stage === "saved", loading = stage === "loading";
      form.hidden = !review; find("[data-pending]").hidden = stage !== "preview";
      find("[data-loading]").hidden = !loading; find("[data-saved]").hidden = !complete;
      find("[data-ai-badge]").hidden = !review && !complete;
      // A real photo is not a sample; spending storage for receipts is not connected yet, so say exactly that.
      const real = source === "photo";
      find("[data-result-title]").textContent = complete ? (real ? "확인한 영수증" : "확인한 샘플 기록") : stage === "preview" ? "인식 준비" : "인식 결과 확인";
      find("[data-ai-badge-text]").textContent = real ? "AI 인식" : "AI 인식 · 샘플";
      find("[data-save-label]").textContent = real ? "확인 완료" : "확인하고 샘플 저장";
      find("[data-saved-heading]").textContent = real ? "영수증 내용을 확인했어요" : "샘플 기록을 남겼어요";
      find("[data-saved-note]").textContent = real ? "지출 내역 저장은 아직 연결되지 않아 이 화면에서만 보여요." : "샘플 저장 결과이며 실제 지출 내역은 바뀌지 않아요.";
      find("[data-result-sub]").textContent = complete ? "아직 지출 내역에는 저장되지 않아요." : "확인하고, 틀린 부분은 바로 고쳐요.";
      find("[data-result-note]").textContent = source === "photo"
        ? (recognized ? "AI가 사진에서 읽은 값이에요. 틀리거나 비어 있는 부분은 직접 고쳐 주세요." : "인식하기를 누르면 사진을 읽어 날짜·가맹점·금액을 채워요.")
        : "아래는 샘플 영수증의 예시 값이에요. 날짜·가맹점·금액을 확인해 주세요.";
      find("[data-missing-notice]").hidden = result.amount !== null;
      find("[data-sample-paper]").hidden = source !== "sample";
      photo.hidden = source !== "photo" || !objectUrl;
      find("[data-empty-photo]").hidden = source !== "photo" || !!objectUrl;
      find("[data-file-name]").textContent = source === "sample" ? "샘플 영수증" : fileName;
      root.querySelectorAll("[data-camera-button], [data-photo-button], [data-use-sample]").forEach(button => { button.disabled = loading; });
      find("[data-result-panel]").setAttribute("aria-busy", String(loading));
      const active = complete ? "saved" : stage === "preview" || loading ? "photo" : "review";
      root.querySelectorAll("[data-step]").forEach(item => {
        item.classList.toggle("receipt-step-current", item.dataset.step === active);
        if (item.dataset.step === active) item.setAttribute("aria-current", "step"); else item.removeAttribute("aria-current");
      });
      if (syncFields) Object.entries(fields).forEach(([name, input]) => { input.value = values[name]; });
      if (complete && saved) {
        find("[data-saved-date]").textContent = saved.date.replaceAll("-", ". ");
        find("[data-saved-merchant]").textContent = saved.merchant;
        find("[data-saved-amount]").textContent = new Intl.NumberFormat("ko-KR").format(saved.amount) + "원";
      }
    }
    function saveReceipt() {
      const draft = Object.fromEntries(Object.entries(fields).map(([name, input]) => [name, input.value]));
      const { errors, record } = validateDraft(draft);
      clearErrors();
      Object.entries(errors).forEach(([name, text]) => {
        const error = find(`[data-error="${name}"]`); error.textContent = text; error.hidden = false; fields[name].setAttribute("aria-invalid", "true");
      });
      if (!record) { Object.values(fields).find(input => input.getAttribute("aria-invalid") === "true").focus(); return; }
      saved = record; values = toDraft(record); stage = "saved"; render();
      const icon = find("[data-success-check]"); icon.classList.remove("receipt-celebrate");
      void icon.offsetWidth;
      icon.classList.add("receipt-celebrate");
      announce(source === "photo" ? "확인한 내용을 화면에 반영했어요." : "수정한 내용을 샘플 기록에 반영했어요.");
      find("[data-result-panel]").scrollIntoView({ behavior: "auto", block: "nearest" });
    }
    find("[data-save]").addEventListener("click", saveReceipt);
    form.addEventListener("submit", event => { event.preventDefault(); saveReceipt(); });
    form.addEventListener("keydown", event => { if (event.key === "Enter" && event.target.tagName === "INPUT") { event.preventDefault(); saveReceipt(); } });
    Object.entries(fields).forEach(([name, input]) => input.addEventListener("input", event => {
      // Preserve the full value for validation instead of the global digits-only filter.
      event.stopPropagation(); values[name] = input.value;
      input.removeAttribute("aria-invalid"); find(`[data-error="${name}"]`).hidden = true; announce("");
    }));
    find("[data-edit]").addEventListener("click", () => { stage = "review"; clearErrors(); render(true); fields.merchant.focus(); announce(source === "photo" ? "내용을 수정한 뒤 다시 확인할 수 있어요." : "내용을 수정한 뒤 다시 샘플 저장할 수 있어요."); });
    find("[data-use-sample]").addEventListener("click", () => {
      generation++; clearTimeout(timer); releasePhoto(); source = "sample"; stage = "preview"; selectedFile = null; recognized = false;
      result = sampleResult(config); values = toDraft(result); saved = null; clearErrors(); render(true); announce("샘플 영수증을 불러왔어요.");
    });
    find("[data-camera-button]").addEventListener("click", () => find("[data-camera-input]").click());
    find("[data-photo-button]").addEventListener("click", () => find("[data-photo-input]").click());
    async function selectFile(input) {
      const file = input.files?.[0]; input.value = "";
      if (!file) return;
      const current = ++generation, error = find("[data-file-error]");
      const fail = text => { error.textContent = text; error.hidden = false; };
      try { validateFile(file); } catch (exception) { fail(exception.message); return; }
      const nextUrl = URL.createObjectURL(file), probe = new Image();
      const decoded = await new Promise(resolve => { probe.onload = () => resolve(true); probe.onerror = () => resolve(false); probe.src = nextUrl; });
      if (current !== generation) { URL.revokeObjectURL(nextUrl); return; }
      if (!decoded) { URL.revokeObjectURL(nextUrl); fail("사진을 열 수 없어요. 다른 JPG·PNG 사진을 선택해 주세요."); return; }
      clearTimeout(timer); releasePhoto(); objectUrl = nextUrl; photo.src = nextUrl; fileName = file.name;
      source = "photo"; stage = "preview"; saved = null; selectedFile = file; recognized = false;
      result = { date: null, merchant: null, amount: null }; values = toDraft(result);
      clearErrors(); render(true); announce("사진 미리보기를 준비했어요. 인식하기를 누르면 사진을 읽어요. 사진은 저장하지 않아요.");
    }
    root.querySelectorAll("[data-camera-input], [data-photo-input]").forEach(input => input.addEventListener("change", () => { selectFile(input); }));
    async function scanPhoto() {
      const current = ++generation, error = find("[data-file-error]");
      const body = new FormData(); body.append("file", selectedFile);
      try {
        const response = await fetch("/api/receipts/scan", { method: "POST", body, credentials: "same-origin", cache: "no-store" });
        const payload = await response.json().catch(() => ({}));
        if (current !== generation) return;
        if (!response.ok) throw new Error(payload.detail || "영수증을 읽지 못했어요. 다시 시도하거나 직접 입력해 주세요.");
        result = contract.fromScanResponse(payload); recognized = payload.source === "ai";
        values = toDraft(result); stage = "review"; clearErrors(); render(true);
        announce(result.amount === null ? "금액을 읽지 못했어요. 직접 입력해 주세요." : "영수증을 읽었어요. 내용을 확인해 주세요.");
        find("[data-result-panel]").scrollIntoView({ behavior: "auto", block: "nearest" });
      } catch (exception) {
        if (current !== generation) return;
        stage = "preview"; render(); error.textContent = exception.message; error.hidden = false;
      }
    }
    find("[data-scan]").addEventListener("click", () => {
      if (stage !== "preview") return;
      stage = "loading"; render();
      if (source === "photo" && selectedFile) { scanPhoto(); return; }
      timer = setTimeout(() => {
        result = sampleResult(config); values = toDraft(result); stage = "review"; clearErrors(); render(true);
        announce(result.amount === null ? "금액 확인이 필요한 샘플 결과예요." : "샘플 인식 결과를 준비했어요.");
        find("[data-result-panel]").scrollIntoView({ behavior: "auto", block: "nearest" });
      }, 450);
    });
    window.addEventListener("pagehide", event => { if (!event.persisted) { generation++; clearTimeout(timer); releasePhoto(); } });
    render(true);
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { MAX_FILE_BYTES, validateFile, parseWon, validDate, validateDraft, sampleResult, toDraft };
  if (typeof document !== "undefined") init();
})();
