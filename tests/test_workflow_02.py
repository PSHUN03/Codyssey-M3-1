import json
from pathlib import Path


def test_inactive_workflow_contract():
    workflow = json.loads((Path(__file__).resolve().parents[1] / "n8n" / "policy_refresh.json").read_text())
    assert not workflow["active"]
    assert workflow["settings"]["timezone"] == "Asia/Seoul"
    assert workflow["settings"]["saveDataSuccessExecution"] == "none"
    names = {n["name"] for n in workflow["nodes"]}
    for source, outputs in workflow["connections"].items():
        assert source in names
        for branch in outputs["main"]:
            assert all(edge["node"] in names for edge in branch)
