"""온통청년 공식 getPlcy JSON API. 인증키·응답 본문을 로그에 남기지 않는다."""

from __future__ import annotations

import logging
import os
import re
from datetime import date

import httpx

# 공급자가 인증키를 query parameter로 요구하므로 httpx의 URL 정보 로그를 끈다.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"


class PolicyAPIError(RuntimeError):
    pass


def normalize(row: dict) -> dict | None:
    category = " ".join(str(row.get(k) or "") for k in ("lclsfNm", "mclsfNm", "plcyKywdNm", "plcyNm"))
    if not any(word in category for word in ("금융", "주거", "세금", "자산", "저축", "월세", "전세", "대출", "장려금")):
        return None
    number, name = str(row.get("plcyNo") or ""), str(row.get("plcyNm") or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", number) or not name:
        raise PolicyAPIError("정책 식별자 또는 이름이 없습니다.")
    detail_url = f"https://www.youthcenter.go.kr/ythip/ythip0020/ythip0020Detail.do?plcyNo={number}"
    return {
        "id": f"youthcenter-{number}", "name": name, "agency": row.get("sprvsnInstCdNm") or "온통청년",
        "category": "주거" if any(w in category for w in ("주거", "월세", "전세")) else "금융·복지",
        "summary": row.get("plcyExplnCn") or name, "benefit": row.get("plcySprtCn") or "공식 공고 확인 필요",
        "eligibility_text": row.get("addAplyQlfcCndCn") or "세부 자격은 공식 공고를 확인하세요.",
        "how_to_apply": row.get("plcyAplyMthdCn") or "공식 정책 상세 페이지 확인",
        "apply_period": row.get("aplyYmd") or "모집 공고 확인 필요",
        "caution": "자동 수집 자료입니다. 자격·모집 기간은 공식 공고 확인이 필요합니다.",
        "rules": {}, "unknown_checks": ["자동 수집 정책의 자격·모집 기간·지역 공식 검수 필요"],
        "estimate": None, "faq": [], "sources": [{"name": "온통청년 정책 상세", "url": detail_url}],
        "review_status": "pending", "collected_on": date.today().isoformat(), "origin": "youthcenter",
    }


def fetch_policies(*, api_key: str | None = None, client=None, max_pages: int = 100) -> list[dict]:
    key = api_key or os.getenv("YOUTHCENTER_API_KEY")
    if not key:
        raise PolicyAPIError("YOUTHCENTER_API_KEY 설정이 필요합니다.")
    owned = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False)
    policies = {}
    try:
        for page in range(1, max_pages + 1):
            try:
                response = client.get(URL, params={"apiKeyNm": key, "pageNum": page,
                                                   "pageSize": 100, "rtnType": "json"})
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError):
                raise PolicyAPIError("온통청년 조회 실패. 인증·네트워크 상태를 확인하세요.") from None
            if not isinstance(body, dict) or str(body.get("resultCode", "200")) not in ("200", "0", "00"):
                raise PolicyAPIError("온통청년 오류 응답입니다. 기존 데이터를 유지합니다.")
            result = body.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("youthPolicyList"), list):
                raise PolicyAPIError("온통청년 응답 형식이 달라졌습니다. 기존 데이터를 유지합니다.")
            rows = result["youthPolicyList"]
            for row in rows:
                policy = normalize(row)
                if policy:
                    policies[policy["id"]] = policy
            pagination = result.get("pagging") or {}
            try:
                total = int(pagination["totCount"]) if "totCount" in pagination else None
            except (TypeError, ValueError):
                raise PolicyAPIError("온통청년 페이지 정보가 올바르지 않습니다.") from None
            if not rows or (total is not None and page * 100 >= total) or (total is None and len(rows) < 100):
                return list(policies.values())
        raise PolicyAPIError("페이지 제한 초과: 부분 수집 자료는 반영하지 않습니다.")
    finally:
        if owned:
            client.close()
