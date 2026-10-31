"""정책 데이터 저장소. 현재는 큐레이션한 JSON 파일이며, 온통청년 API 연동 시 이 모듈을 확장한다."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "policies.json"


@lru_cache
def _load() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def meta() -> dict:
    return _load()["_meta"]


def all_policies() -> list[dict]:
    return _load()["policies"]


def get_policy(policy_id: str) -> dict | None:
    return next((p for p in all_policies() if p["id"] == policy_id), None)


def as_of() -> str:
    return meta()["as_of"]


def chunks(policy: dict) -> list[tuple[str, str]]:
    """검색용 청크 (섹션명, 텍스트). 정책명을 모든 청크에 넣어 이름 검색 정확도를 높인다."""
    name = policy["name"]
    parts = [
        ("개요", f"{name}: {policy['summary']} {policy['benefit']}"),
        ("자격", f"{name} 자격 요건: {policy['eligibility_text']}"),
        ("신청", f"{name} 신청 방법: {policy['how_to_apply']} 신청 기간: {policy['apply_period']}"),
        ("주의", f"{name} 주의할 점: {policy['caution']}"),
    ]
    parts += [("FAQ", f"{name}: {q}") for q in policy.get("faq", [])]
    return parts
