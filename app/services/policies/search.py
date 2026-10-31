"""정책 문서 검색 — BM25 (docs/adr/0003 참고).

정책 코퍼스가 수백 청크 규모라 별도 벡터 DB 없이 메모리 내 BM25로 충분하다.
한국어는 형태소 분석기 없이 음절 바이그램으로 토큰화해 조사·어미 변화에 강하게 만든다.
임베딩 검색을 추가할 때는 search()의 결과와 점수를 합치는 하이브리드 방식으로 확장한다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.services.policies import repository

_WORD_RE = re.compile(r"[0-9a-z]+|[가-힣]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD_RE.findall(text.lower()):
        if word[0] >= "가":  # 한글
            tokens.extend([word] if len(word) == 1 else [word[i:i + 2] for i in range(len(word) - 1)])
        else:
            tokens.append(word)
    return tokens


@dataclass
class Chunk:
    policy_id: str
    section: str
    text: str


@dataclass
class Hit:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c.text)) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q_tokens = tokenize(query)
        scored: list[Hit] = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths, strict=True):
            score = 0.0
            for t in q_tokens:
                tf = doc.get(t)
                if not tf:
                    continue
                norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avgdl))
                score += self.idf[t] * norm
            if score > 0:
                scored.append(Hit(chunk, score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]


@lru_cache
def index() -> BM25Index:
    chunks = [
        Chunk(p["id"], section, text)
        for p in repository.all_policies()
        for section, text in repository.chunks(p)
    ]
    return BM25Index(chunks)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def search_policies(query: str, k: int = 3) -> list[tuple[dict, list[Hit]]]:
    """질문과 관련된 정책을 점수 순으로 k개 돌려준다. 각 정책에는 근거가 된 청크가 붙는다.

    질문에 정책 이름이 그대로 들어 있으면(예: "청년도약계좌 가입돼?") 그 정책을 우선한다.
    다른 정책 문서가 그 이름을 여러 번 언급해 BM25 점수가 더 높게 나오는 경우를 막기 위한 보정이다.
    """
    grouped: dict[str, list[Hit]] = {}
    for hit in index().search(query, k=k * 4):
        grouped.setdefault(hit.chunk.policy_id, []).append(hit)

    q = _compact(query)
    named = {p["id"] for p in repository.all_policies() if _compact(p["name"]) in q}
    for pid in named - grouped.keys():
        grouped[pid] = [Hit(Chunk(pid, "개요", repository.chunks(repository.get_policy(pid))[0][1]), 0.0)]

    def rank(item: tuple[str, list[Hit]]) -> tuple[bool, float]:
        pid, hits = item
        return pid in named, max(h.score for h in hits)

    ranked = sorted(grouped.items(), key=rank, reverse=True)
    return [(repository.get_policy(pid), hits) for pid, hits in ranked[:k]]
