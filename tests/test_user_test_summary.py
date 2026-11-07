"""사용자 테스트 집계 스크립트 계산 검증 (입력은 형식 확인용 고정값)."""

import csv
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "user_test_summary", Path(__file__).resolve().parents[1] / "scripts" / "user_test_summary.py"
)
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)

SUS_TITLES = [f"B{i}. 문항{i}" for i in range(1, 11)]


def _write(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return path


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (["3"] * 10, 50.0),
        (["5", "1"] * 5, 100.0),
        (["1", "5"] * 5, 0.0),
        (["3"] * 9 + [""], None),
    ],
)
def test_sus_score(answers, expected):
    ans = {f"B{i + 1}": v for i, v in enumerate(answers)}
    assert summary.sus_score(ans) == expected


def test_nps():
    assert summary.nps([10, 9, 7, 3]) == 25.0
    assert summary.nps([]) is None


def test_by_code_ignores_untagged_columns():
    row = {"타임스탬프": "2026. 11. 7", "A1. 테스터 번호": " T-01 ", "B10) 문항": "4"}
    assert summary.by_code(row) == {"A1": "T-01", "B10": "4"}


def test_report_from_csv(tmp_path, capsys):
    header = ["타임스탬프", "A1. 번호", "A2. 나이대", "A6. 계정", "F1. 시간"] + SUS_TITLES
    header += ["C2. 맞음", "C5. 추천", "D1. 혜택 수", "E2. 불편", "E4. 재사용"]
    rows = [
        ["t", "T-01", "25~29", "예시 계정", "예시 계정이라 안 함"] + ["5", "1"] * 5
        + ["4", "9", "3개 이상", "버튼이 작아요", "예"],
        ["t", "T-02", "19~24", "직접 가입(실제 정보)", "3~5분"] + ["3"] * 10
        + ["3", "5", "1", "", "모르겠다"],
        ["t", "t-02", "19~24", "직접 가입(실제 정보)", "5~10분"] + ["3"] * 10
        + ["2", "6", "1", "", "아니요"],
    ]
    survey = _write(tmp_path / "survey.csv", header, rows)
    obs = _write(
        tmp_path / "obs.csv",
        ["번호", "T1 진단 완료(분)", "T2 배분 설명", "T3 혜택 찾기", "T4 코치 만족도(1~5)", "T5 약속 저장"],
        [["T-01", "", "O", "O", "5", "O"], ["T-02", "7", "X", "O", "3", ""], ["T-03", "", "", "", "", ""]],
    )

    assert summary.main([str(survey), "--observations", str(obs)]) == 0
    out = capsys.readouterr()
    assert "중복 응답" in out.err and "T-02" in out.err
    assert "| 테스터 수 | 10명 (최소 5명) | 2명 (예시 계정 1명) |" in out.out
    assert "평균 75.0점" in out.out
    assert "평균 2.0개, 2개 이상 50% (1/2)" in out.out
    assert "| 재사용 의향 | 60% 이상 | 50% (1/2) |" in out.out
    assert "진단 5분 이내 완료 (자가 응답) | | 0% (0/1)" in out.out
    assert "과제 성공률 (T1~T5, 관찰 2명) | 80% | 62% (5/8)" in out.out
    assert "- T-01: 버튼이 작아요" in out.out


def test_empty_survey_fails(tmp_path):
    survey = _write(tmp_path / "survey.csv", ["타임스탬프", "질문"], [["t", "x"]])
    assert summary.main([str(survey)]) == 1
