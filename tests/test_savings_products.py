import json

import httpx
import pytest

from app.services import savings_products


def test_fss_join_cache_sort_and_null_rates(tmp_path):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"result": {"err_cd": "000", "max_page_no": 1,
            "baseList": [{"fin_co_no": "bank", "fin_prdt_cd": "product", "kor_co_nm": "가상은행",
                          "fin_prdt_nm": "테스트 상품", "dcls_month": "202610", "spcl_cnd": "급여 이체 조건"}],
            "optionList": [
                {"fin_co_no": "bank", "fin_prdt_cd": "product", "save_trm": "12", "intr_rate": "3.0",
                 "intr_rate2": "4.5"},
                {"fin_co_no": "bank", "fin_prdt_cd": "product", "save_trm": "12", "intr_rate": None}]}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first = savings_products.compare_savings_products(12, api_key="fake", client=client, cache_dir=tmp_path)
        again = savings_products.compare_savings_products(12, client=client, cache_dir=tmp_path)
    assert len(calls) == 1
    assert first == again and len(first["products"]) == 1
    assert first["products"][0]["maximum_rate"] == 4.5
    assert "가입 권유가 아닙니다" in first["notice"]
    assert "fake" not in (tmp_path / "fss-savings.json").read_text()


def test_missing_fss_key_does_not_fake_rates(tmp_path, monkeypatch):
    monkeypatch.delenv("FSS_API_KEY", raising=False)
    with pytest.raises(savings_products.ProductAPIError):
        savings_products.compare_savings_products(12, cache_dir=tmp_path)


def test_fss_failure_keeps_previous_cache(tmp_path):
    path = tmp_path / "fss-savings.json"
    old = {"fetched_on": "2000-01-01", "products": []}
    path.write_text(json.dumps(old))
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(savings_products.ProductAPIError):
            savings_products.compare_savings_products(12, api_key="secret", client=client, cache_dir=tmp_path)
    assert json.loads(path.read_text()) == old



def test_product_api_and_agent_tool_share_comparison(client, monkeypatch):
    from sqlalchemy import select

    from app.db import new_session
    from app.models import User
    from app.services.agent.tools import TOOL_SPECS, ToolContext, run_tool

    assert client.get("/api/products/compare").status_code == 401
    client.post("/demo")
    expected = {"products": [], "notice": savings_products.NOTICE, "is_mock": False, "fetched_on": "2026-11-03"}
    monkeypatch.setattr(savings_products, "compare_savings_products", lambda *a, **kw: expected)
    assert client.get("/api/products/compare").json() == expected
    with new_session() as db:
        user = db.scalar(select(User).where(User.is_demo.is_(True)))
        result, error = run_tool("compare_savings_products", {"term_months": 12}, ToolContext(db, user))
        assert not error and result == expected
    assert any(spec["name"] == "compare_savings_products" for spec in TOOL_SPECS)
