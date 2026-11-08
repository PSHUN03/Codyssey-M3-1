"""금융 기초 학습 카드와 퀴즈 (FR-21). 내용은 app/data/lessons.json 한 곳에서 관리한다."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "lessons.json"


@lru_cache
def load() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))
