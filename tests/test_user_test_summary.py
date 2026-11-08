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
    row = {"타임스탬프": "2026. 11. 8", "A1. 나이대": " 20대 ", "B10) 문항": "4"}
    assert summary.by_code(row) == {"A1": "20대", "B10": "4"}


def test_report_from_csv(tmp_path, capsys):
    header = ["타임스탬프", "P1. 동의", "A1. 나이대", "A3. 첫 월급", "A6. 계정", "U1. 써 본 기능", "U2. 진단 시간"]
    header += ["U3. 가장 도움", *SUS_TITLES, "C5. 코치 반영", "D1. 혜택 수", "E1. 다시", "E2. 추천", "E4. 불편"]
    rows = [
        ["t", "동의합니다", "20대", "1~3년", "예시 계정(가상 인물 지우)으로 둘러봄", "월급 배분 플랜, AI 코치 상담",
         "진단을 하지 않음(예시 계정 등)", "AI 코치 상담", *(["5", "1"] * 5), "4", "3개 이상", "예", "9", "버튼이 작아요"],
        ["t", "동의합니다", "30대", "5년 이상", "직접 가입해 내 실제 정보로", "재무 진단(질문 카드), AI 코치 상담",
         "3~5분", "도움이 된 기능이 없음", *(["3"] * 10), "", "1개", "아마도", "6", ""],
    ]
    survey = _write(tmp_path / "survey.csv", header, rows)
    obs = _write(
        tmp_path / "obs.csv",
        ["번호", "T1 진단 완료(분)", "T2 배분 설명", "T3 혜택 찾기", "T4 코치 만족도(1~5)", "T5 약속 저장"],
        [["T-01", "", "O", "O", "5", "O"], ["T-02", "7", "X", "O", "3", ""], ["T-03", "", "", "", "", ""]],
    )

    assert summary.main([str(survey), "--observations", str(obs)]) == 0
    out = capsys.readouterr().out
    assert "| 응답자 수 | 10명 (최소 5명) | 2명 (예시 계정 1명) |" in out
    assert "평균 75.0점" in out
    assert "평균 2.0개, 2개 이상 50% (1/2)" in out
    assert "| 재사용 의향 ('예') | 60% 이상 | 50% (1/2), 아마도 1명 |" in out
    assert "| 주 대상(첫 소득 3년 이내) | 50% (1/2) |" in out
    assert "진단 5분 이내 완료 (자가 응답) | 80% 이상 | 100% (1/1)" in out
    assert "| NPS | 0 이상 | +0 (2명) |" in out
    assert "| C5 코치 답변이 내 상황을 반영함 | 4.0점 (1명) |" in out
    assert "| AI 코치 상담 | 2명 | 1명 |" in out
    assert "| 도움이 된 기능이 없음 | | 1명 |" in out
    assert "과제 성공률 (T1~T5, 관찰 2명) | 80% | 62% (5/8)" in out
    assert "- 응답 1: 버튼이 작아요" in out


def test_empty_survey_fails(tmp_path):
    survey = _write(tmp_path / "survey.csv", ["타임스탬프", "질문"], [["t", "x"]])
    assert summary.main([str(survey)]) == 1
