import json
from datetime import date

import httpx
import pytest

from app.services import savings_products
from app.services.policies import eligibility, ingest, repository, search, youthcenter
from tests.test_policies import P


def test_no_rules_requires_manual_check():
    policy = {"id": "new", "name": "신규", "rules": {}}
    assert eligibility.evaluate(policy, P()).status == "check"


def test_twenty_policies_have_sources_and_no_unreviewed_auto_eligibility():
    assert len(repository.all_policies()) >= 20
    for policy in repository.all_policies():
        assert policy["sources"]
        if policy.get("review_status") == "pending":
            assert eligibility.evaluate(policy, P()).status != "eligible"


def test_official_future_window():
    policy = repository.get_policy("youth-future-savings")
    assert eligibility.evaluate(policy, P(), today=date(2026, 10, 31)).status == "closed"
    assert eligibility.evaluate(policy, P(), today=date(2026, 10, 12)).status == "check"


def test_youth_api_normalization_paging_and_atomic_ingest(tmp_path, monkeypatch):
    target = tmp_path / "policies.json"
    monkeypatch.setenv("POLICY_EXTERNAL_FILE", str(target))
    calls = []
    def handle(request):
        calls.append(request.url.params["pageNum"])
        assert request.url.params["apiKeyNm"] == "fake-key"
        return httpx.Response(200, json={"resultCode": 200, "result": {
            "pagging": {"totCount": 1}, "youthPolicyList": [{"plcyNo": "123", "plcyNm": "가짜 주거 정책"}]}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        policies = youthcenter.fetch_policies(api_key="fake-key", client=client)
    try:
        search.index()
        assert ingest.ingest(policies, target=target)["added"] == 1
        assert ingest.ingest(policies, target=target)["updated"] == 0
        assert search.search_policies("가짜 주거 정책")[0][0]["id"] == "youthcenter-123"
        assert eligibility.evaluate(policies[0], P()).status == "check"
        before = target.read_bytes()
        with pytest.raises(ValueError):
            ingest.ingest([{"id": "bad"}], target=target)
        assert target.read_bytes() == before
        assert calls == ["1"]
    finally:
        repository._load.cache_clear()
        search.index.cache_clear()


def test_youth_failure_does_not_expose_key():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403))) as client:
        with pytest.raises(youthcenter.PolicyAPIError) as error:
            youthcenter.fetch_policies(api_key="private-fake-key", client=client)
        assert "private-fake-key" not in str(error.value)


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
