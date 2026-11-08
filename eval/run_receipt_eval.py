"""영수증 인식 정확도 평가 (AI-02). eval/receipts/의 가상 영수증 10장과 정답을 비교한다.

실제 Claude 호출이 필요하다 (ANTHROPIC_API_KEY, 필요하면 ANTHROPIC_BASE_URL·FAST_MODEL).

    python eval/run_receipt_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services import receipts  # noqa: E402

SAMPLES = ROOT / "eval" / "receipts"


def score(answers: list[dict], vision_call) -> dict:
    rows = []
    for answer in answers:
        content = (SAMPLES / answer["file"]).read_bytes()
        try:
            result = receipts.scan(content, vision_call=vision_call)
        except receipts.ReceiptError as exc:
            result = {"error": str(exc)}
        rows.append({
            "file": answer["file"],
            "date": result.get("date") == answer["date"],
            "merchant": result.get("merchant_name") == answer["merchant"],
            "total": result.get("total_amount") == answer["total"],  # 정답이 null이면 null이어야 맞다
            "card_masked": "3456" not in json.dumps(result, ensure_ascii=False),
            "got_total": result.get("total_amount"),
            "error": result.get("error"),
        })
    n = len(rows)
    rate = {key: sum(r[key] for r in rows) / n for key in ("date", "merchant", "total", "card_masked")}
    return {"n": n, "accuracy": rate, "rows": rows}


def main() -> int:
    if get_settings().is_mock:
        print("모의 모드에서는 평가할 수 없습니다. ANTHROPIC_API_KEY를 설정하세요.")
        return 1
    from app.services.agent.llm import vision_structured_call

    answers = [json.loads(line) for line in (SAMPLES / "answers.jsonl").read_text(encoding="utf-8").splitlines() if line]
    result = score(answers, vision_structured_call)
    acc = result["accuracy"]
    print(f"[영수증] {result['n']}장  날짜 {acc['date']:.0%}  가맹점 {acc['merchant']:.0%}  "
          f"합계 {acc['total']:.0%}  카드번호 가림 {acc['card_masked']:.0%}  (가상 영수증 기준)")
    for row in result["rows"]:
        missed = [k for k in ("date", "merchant", "total", "card_masked") if not row[k]]
        if missed or row["error"]:
            print(f"  {row['file']}: 틀림 {missed} 합계={row['got_total']} {row['error'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
