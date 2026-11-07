"""사용자 테스트 응답 집계.

구글 폼 응답 CSV와 (있으면) 진행자 관찰 기록 CSV를 읽어 README와 결과보고서에 붙일
Markdown을 출력한다. 폼 문항 제목은 'B1.'처럼 코드와 마침표로 시작해야 한다
(docs/user-test/07_단기테스트_진행키트.md 6절). 응답 파일은 private/에 두고 커밋하지 않는다.

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
F1_WITHIN_5 = {"3분 이내", "3~5분"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def by_code(row: dict[str, str]) -> dict[str, str]:
    """'B1. 이 서비스를…' 같은 열 이름을 'B1' 키로 바꾼다."""
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


def dedupe(responses: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """같은 테스터 번호가 여러 번 응답했으면 마지막 응답만 남긴다."""
    latest: dict[str, dict[str, str]] = {}
    dupes: list[str] = []
    for i, ans in enumerate(responses):
        tid = ans.get("A1", "").upper().replace(" ", "") or f"(번호 없음 {i + 1})"
        if tid in latest:
            dupes.append(tid)
        latest[tid] = ans
    return list(latest.values()), dupes


def summarize_survey(responses: list[dict[str, str]]) -> dict:
    n = len(responses)
    sus = [s for s in (sus_score(a) for a in responses) if s is not None]
    benefits = [v for v in (to_int(a.get("D1")) for a in responses) if v is not None]
    nps_scores = [v for v in (to_int(a.get("C5")) for a in responses) if v is not None and v <= 10]
    reuse = [a.get("E4", "") for a in responses if a.get("E4")]
    f1 = [a.get("F1", "") for a in responses if a.get("F1") and "예시 계정" not in a.get("F1", "")]
    f2 = [a.get("F2", "") for a in responses if a.get("F2")]
    f3 = [a.get("F3", "") for a in responses if a.get("F3") in ("예", "아니요")]
    likert = {
        code: [v for v in (to_int(a.get(code)) for a in responses) if v is not None and 1 <= v <= 5]
        for code in ("C1", "C2", "C3", "C4")
    }
    return {
        "n": n,
        "demo": sum("예시 계정" in a.get("A6", "") for a in responses),
        "sus": sus,
        "benefits": benefits,
        "nps": nps(nps_scores),
        "nps_n": len(nps_scores),
        "reuse_yes": sum(r == "예" for r in reuse),
        "reuse_n": len(reuse),
        "f1_ok": sum(v in F1_WITHIN_5 for v in f1),
        "f1_n": len(f1),
        "f2_ok": sum(v == "예" for v in f2),
        "f2_n": len(f2),
        "f3_ok": sum(v == "예" for v in f3),
        "f3_n": len(f3),
        "likert": likert,
        "age": Counter(a.get("A2", "") for a in responses if a.get("A2")),
        "work": Counter(a.get("A3", "") for a in responses if a.get("A3")),
        "mode": Counter(a.get("A5", "") for a in responses if a.get("A5")),
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
    lines = [
        "## README 표",
        "",
        "| 지표 | 목표 | 결과 |",
        "|---|---|---|",
        f"| 테스터 수 | 10명 (최소 5명) | {n}명 (예시 계정 {survey['demo']}명) |",
        f"| SUS 사용성 점수 | 70점 이상 | {sus_text} |",
        f"| 1인당 새로 알게 된 혜택 | 2개 이상 | {benefit_text} |",
        f"| 재사용 의향 | 60% 이상 | {pct(survey['reuse_yes'], survey['reuse_n'])} |",
        "",
        "혜택 수의 '3개 이상'은 3개로 계산했습니다.",
        "",
        "## 결과보고서 2절 참여자",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 참여 인원 | {n}명 (실제 데이터 {n - survey['demo']}명 / 예시 계정 {survey['demo']}명) |",
        f"| 나이대 분포 | {counter_text(survey['age'])} |",
        f"| 일하는 형태 분포 | {counter_text(survey['work'])} |",
        f"| 참여 방식 | {counter_text(survey['mode'])} |",
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
        f"| 진단 5분 이내 완료 (자가 응답) | | {pct(survey['f1_ok'], survey['f1_n'])} |",
        f"| 혜택 신청 방법 찾음 (자가 응답) | | {pct(survey['f2_ok'], survey['f2_n'])} |",
        f"| 약속 저장 확인 (자가 응답) | | {pct(survey['f3_ok'], survey['f3_n'])} |",
        f"| SUS 점수 | 70점 이상 | {sus_text} |",
        f"| 1인당 새로 알게 된 혜택 | 2개 이상 | {benefit_text} |",
        f"| 코치 답변이 내 상황에 맞음 (C2) | 4.0 이상 | {mean_text(survey['likert']['C2'], '점')} |",
        "| 7일 내 3회 이상 재방문 | 50% 이상 | 측정 안 함 (기간 축소) |",
        f"| 재사용 의향 | 60% 이상 | {pct(survey['reuse_yes'], survey['reuse_n'])} |",
        f"| NPS | 0 이상 | {nps_text} |",
        "",
        "| 가치와 신뢰 문항 | 평균 |",
        "|---|---|",
        f"| C1 배분 이유를 이해함 | {mean_text(survey['likert']['C1'], '점')} |",
        f"| C2 코치 답변이 내 상황에 맞음 | {mean_text(survey['likert']['C2'], '점')} |",
        f"| C3 코치 답변을 믿을 수 있음 | {mean_text(survey['likert']['C3'], '점')} |",
        f"| C4 이번 주 행동이 분명해짐 | {mean_text(survey['likert']['C4'], '점')} |",
    ]
    if obs:
        lines += ["", "| 과제 | 성공 |", "|---|---|"]
        for code, (ok, total) in obs["rates"].items():
            lines.append(f"| {code} | {pct(ok, total)} |")
    lines += ["", "## 자유 의견 (테스터 번호별)", ""]
    for code, title in (
        ("E1", "좋았던 점"),
        ("E2", "불편하거나 헷갈린 점"),
        ("E3", "있으면 계속 쓸 기능"),
        ("D2", "알아볼 혜택"),
    ):
        lines.append(f"### {code} {title}")
        lines.append("")
        items = [(a.get("A1", "?"), a.get(code, "")) for a in responses if a.get(code)]
        lines += [f"- {tid}: {text}" for tid, text in items] or ["- (응답 없음)"]
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
    responses, dupes = dedupe(responses)
    if dupes:
        print(f"같은 번호의 중복 응답은 마지막 것만 썼습니다: {', '.join(sorted(set(dupes)))}", file=sys.stderr)

    obs = None
    if args.observations and args.observations.exists():
        obs = summarize_observations(read_csv(args.observations))
    print(render(summarize_survey(responses), obs, responses))
    return 0


if __name__ == "__main__":
    sys.exit(main())
