import io
import json

import pytest
from openpyxl import Workbook

from app.services.transactions import MAX_BYTES, parse_transactions


@pytest.mark.parametrize("headers", [
    "거래일시,적요,출금액,입금액",  # 국민 형식 모의
    "거래일자,내용,출금금액,입금금액",  # 신한 형식 모의
    "거래일시,거래내용,출금,입금",  # 카카오 형식 모의
])
def test_bank_layouts_and_signs(headers):
    content = (headers + "\n2026-10-01,스타벅스,5000,\n2026-10-02,급여,,2500000").encode()
    result = parse_transactions(content, "fake.csv")
    assert not result["errors"]
    assert result["transactions"][0]["amount"] == -5000
    assert result["transactions"][0]["category"] == "식비"
    assert result["transactions"][1]["amount"] == 2500000


def test_cp949_preamble_and_sensitive_numbers():
    content = "계좌번호 123-45-678901\n거래일,적요,출금액\n2026.10.01,이체 12345678901234,1000".encode("cp949")
    result = parse_transactions(content, "fake.csv")
    assert "12345678901234" not in json.dumps(result)
    assert result["header_row"] == 1


def test_xlsx_and_formula():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["거래일", "거래내용", "출금액", "계좌번호"])
    sheet.append(["2026-10-01", "=HYPERLINK(\"https://invalid.test\")", 3000, "1234567890123"])
    stream = io.BytesIO()
    workbook.save(stream)
    result = parse_transactions(stream.getvalue(), "sample.xlsx")
    assert result["transactions"][0]["merchant"] == "[수식 제외]"


def test_llm_only_receives_masked_preview_and_minimal_categories():
    calls = []
    def mock(system, user, **kwargs):
        calls.append(json.loads(user))
        if len(calls) == 1:
            return {"header_row": 0, "mapping": {"date": 0, "merchant": 1, "withdrawal": 2}}
        return {"categories": ["쇼핑"]}
    content = "a,b,c\n2026-10-01,매장 1234-5678-9012-3456,5000".encode()
    result = parse_transactions(content, "sample.csv", structured_call=mock)
    assert "1234-5678-9012-3456" not in json.dumps(calls)
    assert set(calls[1][0]) == {"merchant", "amount"}
    assert result["transactions"][0]["category"] == "쇼핑"


@pytest.mark.parametrize("money", ["NaN", "Infinity", "12.5", "1000000001", "not-money"])
def test_bad_amounts_are_not_silently_changed(money):
    result = parse_transactions(f"거래일,적요,출금액\n2026-10-01,테스트,{money}".encode(), "fake.csv")
    assert not result["transactions"] and result["errors"]


def test_ambiguous_positive_amount_needs_direction():
    result = parse_transactions("날짜,가맹점,금액\n2026-10-01,상점,5000".encode(), "fake.csv",
                                mapping={"date": 0, "merchant": 1, "amount": 2})
    assert result["errors"]


def test_unknown_layout_returns_safe_mapping_preview():
    result = parse_transactions("unknown,columns\n계좌 123456789012,내용".encode(), "fake.csv")
    assert result["needs_mapping"]
    assert "123456789012" not in str(result)


@pytest.mark.parametrize("content,filename", [(b"a" * (MAX_BYTES + 1), "x.csv"), (b"test", "x.xls")])
def test_file_limits(content, filename):
    with pytest.raises(ValueError):
        parse_transactions(content, filename)
