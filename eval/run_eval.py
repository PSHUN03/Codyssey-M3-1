"""AI 품질 평가 (NFR-03, NFR-04). 결과는 docs/devlog 에 기록해 개선 전후를 비교한다.

실행:
    python eval/run_eval.py              # 검색 품질 + 투자 권유 탐지 (API 키 불필요, 비용 0원)
    python eval/run_eval.py --live       # 실제 Claude 코치 응답까지 평가 (ANTHROPIC_API_KEY 필요, 비용 발생)

평가 항목
1. 검색 정답률(hit@1, hit@3): 질문에 맞는 정책이 검색 1위/3위 안에 드는가
2. 근거 포함률: 1위 정책 문서에 정답 핵심어(must_include)가 들어 있는가
3. 투자 권유 탐지율: 레드팀 질문을 입력 가드레일이 잡아내는가
4. (--live) 레드팀 응답에 투자 권유 문구가 섞이지 않는가 — 목표 위반 0건
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.agent.guardrails import (  # noqa: E402
    contains_investment_advice,
    is_investment_advice_request,
)
from app.services.policies import repository  # noqa: E402
from app.services.policies.search import search_policies  # noqa: E402


def load(name: str) -> list[dict]:
    lines = (ROOT / "eval" / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def eval_retrieval() -> dict:
    rows = load("golden_policy_qa.jsonl")
    hit1 = hit3 = grounded = 0
    failures = []
    for row in rows:
        ranked = [p["id"] for p, _ in search_policies(row["question"], k=3)]
        if ranked[:1] == [row["expected_policy"]]:
            hit1 += 1
        if row["expected_policy"] in ranked:
            hit3 += 1
        else:
            failures.append((row["id"], row["question"], ranked))
        policy = repository.get_policy(row["expected_policy"])
        corpus = " ".join(text for _, text in repository.chunks(policy))
        if all(word in corpus for word in row["must_include"]):
            grounded += 1
    n = len(rows)
    return {"n": n, "hit@1": hit1 / n, "hit@3": hit3 / n, "grounded": grounded / n, "failures": failures}


def eval_guardrail_detection() -> dict:
    rows = load("redteam.jsonl")
    missed = [r["prompt"] for r in rows if not is_investment_advice_request(r["prompt"])]
    return {"n": len(rows), "detected": 1 - len(missed) / len(rows), "missed": missed}


def eval_live_redteam() -> dict:
    """실제 코치 응답 평가. 가드레일을 거치지 않고 모델이 스스로 원칙을 지키는지 확인한다."""
    import os

    os.environ.setdefault("LLM_PROVIDER", "anthropic")
    from app.config import get_settings
    from app.db import init_engine, new_session
    from app.services import account
    from app.services.agent.coach import AnthropicCoach
    from app.services.agent.tools import ToolContext

    get_settings.cache_clear()
    init_engine("sqlite:///:memory:")
    db = new_session()
    user = account.create_demo_user(db)
    violations = []
    for row in load("redteam.jsonl"):
        ctx = ToolContext(db=db, user=user)
        text = "".join(e["text"] for e in AnthropicCoach().stream(ctx, [], row["prompt"]) if e["type"] == "delta")
        if contains_investment_advice(text):
            violations.append((row["id"], text[:200]))
    return {"n": len(load("redteam.jsonl")), "violations": violations}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="실제 Claude API로 레드팀 응답까지 평가 (비용 발생)")
    args = parser.parse_args()

    r = eval_retrieval()
    print(f"[검색] {r['n']}문항  hit@1 {r['hit@1']:.0%}  hit@3 {r['hit@3']:.0%}  근거 포함 {r['grounded']:.0%}")
    for fid, q, ranked in r["failures"]:
        print(f"  실패 {fid}: {q} → {ranked}")

    g = eval_guardrail_detection()
    print(f"[가드레일] {g['n']}문항  투자 권유 요청 탐지 {g['detected']:.0%}")
    for m in g["missed"]:
        print(f"  미탐지: {m}")

    if args.live:
        live = eval_live_redteam()
        print(f"[라이브 레드팀] {live['n']}문항  위반 {len(live['violations'])}건")
        for vid, text in live["violations"]:
            print(f"  위반 {vid}: {text}")


if __name__ == "__main__":
    main()
