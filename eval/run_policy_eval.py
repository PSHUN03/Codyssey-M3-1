"""개발용/PM 골든셋을 명시적으로 구분하는 정책 검색 평가."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.policies import repository  # noqa: E402
from app.services.policies.search import search_policies  # noqa: E402


def evaluate(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("평가셋이 비어 있습니다.")
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError("평가 ID 중복입니다.")
    failures, hit1, hit3, grounded = [], 0, 0, 0
    for row in rows:
        if repository.get_policy(row["expected_policy"]) is None:
            raise ValueError(f"정답 정책이 없습니다: {row['id']}")
        results = search_policies(row["question"], 3)
        ranked = [p["id"] for p, _ in results]
        ok = ranked[:1] == [row["expected_policy"]]
        hit1 += ok
        hit3 += row["expected_policy"] in ranked
        # 전체 문서가 아니라 실제 반환된 1위 정책의 근거 청크에서 확인한다.
        evidence = " ".join(h.chunk.text for h in results[0][1]) if results else ""
        grounded += bool(ok and all(word in evidence for word in row.get("must_include", [])))
        if not ok:
            failures.append({"id": row["id"], "question": row["question"], "ranked": ranked})
    return {"dataset": path.name, "n": len(rows), "hit@1": hit1 / len(rows), "hit@3": hit3 / len(rows),
            "retrieved_evidence_coverage": grounded / len(rows), "failures": failures,
            "review_status": "development_draft" if any("review_status" in r for r in rows) else "legacy_or_pm"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "eval" / "draft_policy_qa.jsonl")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
