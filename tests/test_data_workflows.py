import json
from pathlib import Path

import pytest

from app.services.transactions import parse_transactions

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["kb_fake.csv", "shinhan_fake.xlsx", "kakao_fake.csv"])
def test_synthetic_bank_files(name):
    path = ROOT / "tests" / "fixtures" / "transactions" / name
    result = parse_transactions(path.read_bytes(), name)
    assert not result["needs_mapping"] and not result["errors"]
    assert len(result["transactions"]) == 2


@pytest.mark.parametrize("name", ["weekly_checkin.json", "policy_refresh.json"])
def test_workflow_structure_and_inactive_delivery(name):
    workflow = json.loads((ROOT / "n8n" / name).read_text())
    assert not workflow["active"]
    assert workflow["settings"]["timezone"] == "Asia/Seoul"
    assert workflow["settings"]["saveDataSuccessExecution"] == "none"
    names = {n["name"] for n in workflow["nodes"]}
    assert len(names) == len(workflow["nodes"])
    for source, outputs in workflow["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            for edge in branch:
                assert edge["node"] in names
    for node in workflow["nodes"]:
        if node["name"] in ("정책 갱신", "리포트 준비", "발송 선점", "발송 완료"):
            assert node["parameters"]["genericAuthType"] == "httpHeaderAuth"
