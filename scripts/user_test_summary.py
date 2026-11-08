"""사용자 테스트 응답 집계.

구글 폼 응답 CSV와 (있으면) 진행자 관찰 기록 CSV를 읽어 README와 결과보고서에 붙일
Markdown을 출력한다. 폼 문항 제목은 'B1.'처럼 코드와 마침표로 시작해야 한다
(문항은 docs/user-test/03_설문지.md). 응답 파일은 private/에 두고 커밋하지 않는다.

    python scripts/user_test_summary.py private/설문응답.csv \
        --observations private/사용자테스트_관리.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

CODE_RE = re.compile(r"^\s*([A-Z]\d{1,2})[.)]")
SUCCESS = {"o", "ㅇ", "성공", "예", "y", "yes", "1", "true"}
FAIL = {"x", "실패", "아니요", "n", "no", "0", "false"}
DIAG_WITHIN_5 = {"3분 이내", "3~5분"}
EARLY_CAREER = {"1년 미만", "1~3년"}
FEATURE_ITEMS = (
    ("C1", "재무 진단 질문이 이해하기 쉬움"),
    ("C2", "배분 금액의 이유를 이해함"),
    ("C3", "배분이 실제 생활에 맞음"),
    ("C4", "혜택 자격과 이유가 분명함"),
    ("C5", "코치 답변이 내 상황을 반영함"),
    ("C6", "코치의 금액·정보를 믿을 수 있음"),
    ("C7", "AI 답변 표시와 한계 안내를 알아봄"),
    ("C8", "재무 정보 입력이 부담스럽지 않음"),
    ("C9", "이번 달 실천할 행동이 생김"),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def by_code(row: dict[str, str]) -> dict[str, str]:
    """'B1. 사다리를 자주…' 같은 열 이름을 'B1' 키로 바꾼다."""
    out: dict[str, str] = {}
    for key, value in row.items():
        if not key:
            continue
        m = CODE_RE.match(key)
        if m:
            out[m.group(1)] = (value or "").strip()
    return out


def to_int(value: str | None) -> int | None:
    m = re.search(r"\d+", value or "")
    return int(m.group()) if m else None


def sus_score(ans: dict[str, str]) -> float | None:
    vals = [to_int(ans.get(f"B{i}")) for i in range(1, 11)]
    if any(v is None or not 1 <= v <= 5 for v in vals):
        return None
    total = sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(vals))
    return total * 2.5


def nps(scores: list[int]) -> float | None:
    if not scores:
        return None
    promoters = sum(s >= 9 for s in scores)
    detractors = sum(s <= 6 for s in scores)
    return (promoters - detractors) / len(scores) * 100


def pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:.0f}% ({part}/{whole})" if whole else "응답 없음"


def mean_text(values: list[float], unit: str = "", digits: int = 1) -> str:
    if not values:
        return "응답 없음"
    return f"{statistics.mean(values):.{digits}f}{unit} ({len(values)}명)"


def multi(value: str) -> list[str]:
    """체크박스 응답('가, 나')을 항목 목록으로 나눈다."""
    return [v.strip() for v in value.split(", ") if v.strip()]


def summarize_survey(responses: list[dict[str, str]]) -> dict:
    sus = [s for s in (sus_score(a) for a in responses) if s is not None]
    benefits = [v for v in (to_int(a.get("D1")) for a in responses) if v is not None]
    nps_scores = [v for v in (to_int(a.get("E2")) for a in responses) if v is not None and v <= 10]
    reuse = Counter(a["E1"] for a in responses if a.get("E1"))
    diag = [a["U2"] for a in responses if a.get("U2") and "하지 않음" not in a["U2"]]
    likert = {
        code: [v for v in (to_int(a.get(code)) for a in responses) if v is not None and 1 <= v <= 5]
        for code, _ in FEATURE_ITEMS
    }
    used = Counter(f for a in responses for f in multi(a.get("U1", "")))
    return {
        "n": len(responses),
        "demo": sum("예시 계정" in a.get("A6", "") for a in responses),
        "sus": sus,
        "benefits": benefits,
        "nps": nps(nps_scores),
        "nps_n": len(nps_scores),
        "reuse": reuse,
        "reuse_n": sum(reuse.values()),
        "diag_ok": sum(v in DIAG_WITHIN_5 for v in diag),
        "diag_n": len(diag),
        "likert": likert,
        "age": Counter(a["A1"] for a in responses if a.get("A1")),
        "work": Counter(a["A2"] for a in responses if a.get("A2")),
        "career": Counter(a["A3"] for a in responses if a.get("A3")),
        "early": sum(a.get("A3") in EARLY_CAREER for a in responses),
        "habit": Counter(h for a in responses for h in multi(a.get("A4", ""))),
        "benefit_exp": Counter(a["A5"] for a in responses if a.get("A5")),
        "used": used,
        "best": Counter(a["U3"] for a in responses if a.get("U3")),
    }


def judge(value: str) -> bool | None:
    v = value.strip().lower()
    if v in SUCCESS:
        return True
    if v in FAIL:
        return False
    return None


def summarize_observations(rows: list[dict[str, str]]) -> dict | None:
    observed = [
        r
        for r in rows
        if any((r.get(k) or "").strip() for k in r if k and re.match(r"T[1-5] ", k))
    ]
    if not observed:
        return None
    minutes: list[float] = []
    t1_ok = t1_n = 0
    for r in observed:
        raw = (r.get("T1 진단 완료(분)") or "").strip()
        if not raw:
            continue
        t1_n += 1
        try:
            m = float(raw)
        except ValueError:
            continue  # 'X' = 못 끝냄
        minutes.append(m)
        t1_ok += m <= 5
    result = {"n": len(observed), "t1_median": statistics.median(minutes) if minutes else None}
    rates = {"T1": (t1_ok, t1_n)}
    for code, col in (("T2", "T2 배분 설명"), ("T3", "T3 혜택 찾기"), ("T5", "T5 약속 저장")):
        judged = [j for j in (judge(r.get(col) or "") for r in observed) if j is not None]
        rates[code] = (sum(judged), len(judged))
    t4 = [v for v in (to_int(r.get("T4 코치 만족도(1~5)")) for r in observed) if v and 1 <= v <= 5]
    rates["T4"] = (sum(v >= 4 for v in t4), len(t4))
    result["rates"] = rates
    result["t4"] = t4
    done = [rates[k] for k in ("T1", "T2", "T3", "T4", "T5") if rates[k][1]]
    result["overall"] = (sum(ok for ok, _ in done), sum(n for _, n in done))
    return result


def counter_text(c: Counter) -> str:
    return ", ".join(f"{k} {v}명" for k, v in c.most_common()) or "응답 없음"


def render(survey: dict, obs: dict | None, responses: list[dict[str, str]]) -> str:
    n = survey["n"]
    sus = survey["sus"]
    sus_text = (
        f"평균 {statistics.mean(sus):.1f}점, 중앙값 {statistics.median(sus):.1f}점 ({len(sus)}명)"
        if sus
        else "응답 없음"
    )
    b = survey["benefits"]
    benefit_text = (
        f"평균 {statistics.mean(b):.1f}개, 2개 이상 {pct(sum(v >= 2 for v in b), len(b))}"
        if b
        else "응답 없음"
    )
    nps_text = f"{survey['nps']:+.0f} ({survey['nps_n']}명)" if survey["nps"] is not None else "응답 없음"
    reuse = survey["reuse"]
    reuse_text = pct(reuse.get("예", 0), survey["reuse_n"])
    if reuse.get("아마도"):
        reuse_text += f", 아마도 {reuse['아마도']}명"
    lines = [
        "## README 표",
        "",
        "| 지표 | 목표 | 결과 |",
        "|---|---|---|",
        f"| 응답자 수 | 10명 (최소 5명) | {n}명 (예시 계정 {survey['demo']}명) |",
        f"| SUS 사용성 점수 | 70점 이상 | {sus_text} |",
        f"| 1인당 새로 알게 된 혜택 | 2개 이상 | {benefit_text} |",
        f"| 재사용 의향 ('예') | 60% 이상 | {reuse_text} |",
        "",
        "혜택 수의 '3개 이상'은 3개로 계산했습니다.",
        "",
        "## 결과보고서 2절 응답자",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 응답자 수 | {n}명 (직접 가입 {n - survey['demo']}명 / 예시 계정 {survey['demo']}명) |",
        f"| 주 대상(첫 소득 3년 이내) | {pct(survey['early'], n)} |",
        f"| 나이대 | {counter_text(survey['age'])} |",
        f"| 하고 있는 일 | {counter_text(survey['work'])} |",
        f"| 첫 소득 이후 기간 | {counter_text(survey['career'])} |",
        f"| 돈 관리 방식 (복수 응답) | {counter_text(survey['habit'])} |",
        f"| 청년 혜택 신청 경험 | {counter_text(survey['benefit_exp'])} |",
        "",
        "## 결과보고서 3절 핵심 지표",
        "",
        "| 지표 | 목표 | 결과 |",
        "|---|---|---|",
    ]
    if obs:
        ok, total = obs["overall"]
        median = f"{obs['t1_median']:.1f}분" if obs["t1_median"] is not None else "기록 없음"
        lines += [
            f"| 과제 성공률 (T1~T5, 관찰 {obs['n']}명) | 80% | {pct(ok, total)} |",
            f"| 진단 완료 시간 (중앙값, 관찰) | 5분 이내 | {median} |",
            f"| 코치 답변 만족도 (관찰) | 4.0 이상 | {mean_text([float(v) for v in obs['t4']], '점')} |",
        ]
    lines += [
        f"| 진단 5분 이내 완료 (자가 응답) | 80% 이상 | {pct(survey['diag_ok'], survey['diag_n'])} |",
        f"| SUS 점수 | 70점 이상 | {sus_text} |",
        f"| 1인당 새로 알게 된 혜택 | 2개 이상 | {benefit_text} |",
        f"| 코치 답변이 내 상황을 반영함 (C5) | 4.0 이상 | {mean_text(survey['likert']['C5'], '점')} |",
        "| 7일 내 3회 이상 재방문 | 50% 이상 | 측정 안 함 |",
        f"| 재사용 의향 ('예') | 60% 이상 | {reuse_text} |",
        f"| NPS | 0 이상 | {nps_text} |",
        "",
        "| 기능별 평가 (1~5점) | 평균 |",
        "|---|---|",
    ]
    lines += [f"| {code} {label} | {mean_text(survey['likert'][code], '점')} |" for code, label in FEATURE_ITEMS]
    lines += [
        "",
        "| 기능 | 써 본 사람 | 가장 도움이 됨 |",
        "|---|---|---|",
    ]
    features = list(dict.fromkeys(list(survey["used"]) + [k for k in survey["best"] if "없음" not in k]))
    lines += [f"| {f} | {survey['used'].get(f, 0)}명 | {survey['best'].get(f, 0)}명 |" for f in features]
    if survey["best"].get("도움이 된 기능이 없음"):
        lines.append(f"| 도움이 된 기능이 없음 | | {survey['best']['도움이 된 기능이 없음']}명 |")
    if obs:
        lines += ["", "| 과제 | 성공 |", "|---|---|"]
        for code, (ok, total) in obs["rates"].items():
            lines.append(f"| {code} | {pct(ok, total)} |")
    lines += ["", "## 자유 의견 (응답 순서 번호)", ""]
    for code, title in (
        ("E3", "좋았던 점"),
        ("E4", "헷갈리거나 불편했던 점"),
        ("E5", "바뀌거나 추가되면 계속 쓸 것"),
        ("D2", "더 알아볼 혜택"),
    ):
        lines.append(f"### {code} {title}")
        lines.append("")
        items = [(i, a[code]) for i, a in enumerate(responses, 1) if a.get(code)]
        lines += [f"- 응답 {i}: {text}" for i, text in items] or ["- (응답 없음)"]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="사용자 테스트 응답 집계")
    parser.add_argument("survey", type=Path, help="구글 폼 응답 CSV")
    parser.add_argument("--observations", type=Path, help="진행자 관찰 기록 CSV")
    args = parser.parse_args(argv)

    responses = [by_code(r) for r in read_csv(args.survey)]
    responses = [a for a in responses if any(a.values())]
    if not responses:
        print("응답이 없거나 문항 제목이 'B1.'처럼 코드로 시작하지 않습니다.", file=sys.stderr)
        return 1

    obs = None
    if args.observations and args.observations.exists():
        obs = summarize_observations(read_csv(args.observations))
    print(render(summarize_survey(responses), obs, responses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
