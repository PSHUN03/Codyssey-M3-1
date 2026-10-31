"""비밀번호 해시와 민감정보 마스킹 (NFR-05, NFR-06)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

# scrypt 파라미터: 표준 라이브러리만으로 안전한 해시를 만든다
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        expected = _unb64(digest)
        calc = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return algo == "scrypt" and hmac.compare_digest(calc, expected)


# 순서가 중요하다: 전화번호를 계좌번호보다 먼저 가린다.
# \b 대신 (?<!\d)/(?!\d)를 쓴다: "456789로"처럼 숫자 뒤에 조사가 붙으면 한글도 단어 문자라 \b가 성립하지 않는다.
_S, _E = r"(?<!\d)", r"(?!\d)"
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("주민등록번호", re.compile(_S + r"\d{6}\s?-\s?[1-4]\d{6}" + _E)),
    ("카드번호", re.compile(_S + r"(?:\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}|\d{16})" + _E)),
    ("전화번호", re.compile(_S + r"01[016789][- ]?\d{3,4}[- ]?\d{4}" + _E)),
    ("계좌번호", re.compile(_S + r"\d{3,6}-\d{2,6}-\d{3,7}(?:-\d{1,3})?" + _E)),
]


def mask_sensitive(text: str) -> tuple[str, list[str]]:
    """주민번호·카드·전화·계좌번호를 가리고, 무엇을 가렸는지 함께 돌려준다."""
    found: list[str] = []
    for label, pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            found.append(label)
            text = pattern.sub(f"[{label} 가림]", text)
    return text, found
