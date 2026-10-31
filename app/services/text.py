"""한국어 문장 다듬기 도우미. '정규직(으)로' 같은 기계적인 조사 표기를 피한다."""

from __future__ import annotations

# 숫자를 한글로 읽었을 때 받침이 있는지 (영·일·삼·육·칠·팔은 받침 있음)
_DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False,
                  "5": False, "6": True, "7": True, "8": True, "9": False}
_RIEUL_DIGITS = {"1", "7", "8"}  # 일·칠·팔은 ㄹ 받침


def _last_sound(word: str) -> tuple[bool, bool] | None:
    """(받침 여부, ㄹ 받침 여부). 판단할 수 없으면 None."""
    for ch in reversed(word.strip()):
        if "가" <= ch <= "힣":
            jong = (ord(ch) - 0xAC00) % 28
            return jong != 0, jong == 8
        if ch.isdigit():
            return _DIGIT_BATCHIM[ch], ch in _RIEUL_DIGITS
        if ch in ")]}'\"% ":
            continue
        return None
    return None


def josa(word: str, pair: str) -> str:
    """josa("정규직", "으로/로") → "정규직으로", josa("사과", "을/를") → "사과를"."""
    with_batchim, without = pair.split("/")
    sound = _last_sound(word)
    if sound is None:
        return word + without
    has_batchim, rieul = sound
    if pair == "으로/로":
        return word + ("로" if not has_batchim or rieul else "으로")
    return word + (with_batchim if has_batchim else without)
