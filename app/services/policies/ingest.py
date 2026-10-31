"""검수 시드와 API 자료를 분리 저장. 실패 시 기존 자료 유지, 교체 후 캐시 초기화."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from app.services.policies import repository, search

LOCK = threading.Lock()


def ingest(policies: list[dict], *, target: Path | None = None) -> dict:
    target = target or repository.external_file()
    if any(p.get("origin") != "youthcenter" or not p.get("id", "").startswith("youthcenter-") for p in policies):
        raise ValueError("자동 수집 정책만 반영할 수 있습니다.")
    if len({p["id"] for p in policies}) != len(policies):
        raise ValueError("중복 정책 ID입니다.")
    for policy in policies:
        repository.chunks(policy)  # 저장 전 필수 필드를 검증한다.
    with LOCK:
        old = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"policies": []}
        by_id = {p["id"]: p for p in old["policies"]}
        added = updated = 0
        for policy in policies:
            previous = by_id.get(policy["id"])
            if previous is None:
                added += 1
            elif {k: v for k, v in previous.items() if k != "collected_on"} != {
                k: v for k, v in policy.items() if k != "collected_on"
            }:
                updated += 1
            by_id[policy["id"]] = policy
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=".policies-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"policies": list(by_id.values())}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        repository._load.cache_clear()
        search.index.cache_clear()
    return {"added": added, "updated": updated, "total": len(by_id)}
