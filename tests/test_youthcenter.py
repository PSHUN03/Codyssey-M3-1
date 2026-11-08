import httpx
import pytest

from app.services.policies import eligibility, ingest, repository, search, youthcenter
from tests.test_policies import P


def test_no_rules_requires_manual_check():
    policy = {"id": "new", "name": "신규", "rules": {}}
    assert eligibility.evaluate(policy, P()).status == "check"


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



def test_internal_ingest_route_auth_and_updated_search(client, monkeypatch, tmp_path):
    monkeypatch.setenv("POLICY_EXTERNAL_FILE", str(tmp_path / "external.json"))
    assert client.post("/internal/policies/ingest").status_code == 401
    policy = youthcenter.normalize({"plcyNo": "route123", "plcyNm": "라우트검증 주거 대출"})
    monkeypatch.setattr(youthcenter, "fetch_policies", lambda: [policy])
    try:
        response = client.post("/internal/policies/ingest", headers={"X-Internal-Key": "test-internal-key"})
        assert response.status_code == 200 and response.json()["added"] == 1
        assert repository.get_policy("youthcenter-route123") is not None
    finally:
        repository._load.cache_clear()
        search.index.cache_clear()
