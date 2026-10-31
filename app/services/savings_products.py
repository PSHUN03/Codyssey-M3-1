"""DATA-03: 금감원 공시 비교. 모의 자료를 실제 금리로 표시하지 않는다."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

NOTICE = "정보 제공 목적이며 가입 권유가 아닙니다. 우대 조건과 최신 공시는 금융회사에서 확인하세요."
KST = timezone(timedelta(hours=9))
LOCK = threading.Lock()
ENDPOINTS = {"savings": "savingProductsSearch", "deposit": "depositProductsSearch"}


class ProductAPIError(RuntimeError):
    pass


def _rate(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 <= number <= 100 else None
    except (TypeError, ValueError):
        return None


def _fetch(product_type: str, api_key: str, client) -> list[dict]:
    products, options = {}, []
    url = f"https://finlife.fss.or.kr/finlifeapi/{ENDPOINTS[product_type]}.json"
    for page in range(1, 101):
        try:
            response = client.get(url, params={"auth": api_key, "topFinGrpNo": "020000", "pageNo": page})
            response.raise_for_status()
            data = response.json()["result"]
            if str(data.get("err_cd", "000")) != "000":
                raise ProductAPIError("금감원 API 오류. 인증키와 이용 한도를 확인하세요.")
            base, page_options = data["baseList"], data["optionList"]
            for item in base:
                products[(item["fin_co_no"], item["fin_prdt_cd"])] = item
            options.extend(page_options)
            last = int(data.get("max_page_no", 1))
            if page >= last:
                break
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise ProductAPIError("금감원 조회 실패. 이전 캐시는 유지합니다.") from None
    else:
        raise ProductAPIError("페이지 제한 초과: 부분 자료를 사용하지 않습니다.")
    rows = []
    for option in options:
        base = products.get((option.get("fin_co_no"), option.get("fin_prdt_cd")))
        basic, maximum = _rate(option.get("intr_rate")), _rate(option.get("intr_rate2"))
        if not base or basic is None:
            continue
        try:
            months = int(option["save_trm"])
        except (KeyError, ValueError, TypeError):
            continue
        rows.append({"bank_id": base["fin_co_no"], "bank": base.get("kor_co_nm"), "name": base.get("fin_prdt_nm"),
                     "product_id": base["fin_prdt_cd"], "term_months": months,
                     "base_rate": basic, "maximum_rate": maximum,
                     "preferential_conditions": base.get("spcl_cnd") or "공시 확인 필요",
                     "join_conditions": base.get("join_member"), "join_deny": base.get("join_deny"),
                     "interest_type": option.get("intr_rate_type_nm"),
                     "saving_type": option.get("rsrv_type_nm"), "disclosure_month": base.get("dcls_month"),
                     "disclosed_at": base.get("fin_co_subm_day"), "end_date": base.get("dcls_end_day"),
                     "source": "https://finlife.fss.or.kr/"})
    return rows


def compare_savings_products(term_months: int, product_type: str = "savings", *,
                             api_key: str | None = None, client=None, cache_dir: Path | None = None) -> dict:
    if type(term_months) is not int or not 1 <= term_months <= 120 or product_type not in ENDPOINTS:
        raise ValueError("기간은 1~120개월, 상품 종류는 savings 또는 deposit이어야 합니다.")
    cache_dir = cache_dir or Path(__file__).resolve().parents[1] / "data" / "cache"
    path = cache_dir / f"fss-{product_type}.json"
    now = datetime.now(KST)
    with LOCK:
        cache = None
        if path.exists():
            try:
                cache = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        if cache is None or cache.get("fetched_on") != now.date().isoformat():
            key = api_key or os.getenv("FSS_API_KEY")
            if not key:
                raise ProductAPIError("FSS_API_KEY 설정이 필요합니다. 실제 공시를 조회하지 않았습니다.")
            owned = client is None
            connection = client or httpx.Client(timeout=20, follow_redirects=False)
            try:
                rows = _fetch(product_type, key, connection)
            finally:
                if owned:
                    connection.close()
            cache = {"fetched_on": now.date().isoformat(), "products": rows}
            cache_dir.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=cache_dir, prefix=".fss-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(cache, stream, ensure_ascii=False)
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
    today = now.strftime("%Y%m%d")
    rows = [p for p in cache["products"] if p["term_months"] == term_months
            and (not p.get("end_date") or str(p["end_date"]) >= today)]
    # 기본금리 기준 비교이며 최고금리 충족을 가정하지 않는다.
    rows.sort(key=lambda p: (-p["base_rate"], p["bank"] or "", p["name"] or ""))
    unique = {}
    for product in rows:
        unique.setdefault((product["bank_id"], product["product_id"]), product)
    return {"products": list(unique.values())[:5], "sorted_by": "base_rate", "fetched_on": cache["fetched_on"],
            "product_type": product_type, "notice": NOTICE, "is_mock": False}
