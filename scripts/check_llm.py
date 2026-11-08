"""Claude API 연결 점검. 키 값은 출력하지 않는다.

    python scripts/check_llm.py

.env를 앱과 같은 방식으로 읽은 뒤, 키가 제대로 들어왔는지와 실제 호출 결과(오류 종류)를 알려 준다.
호출은 아주 짧은 요청 2번이라 비용은 1원 안팎이다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_DIR / ".env"


def check_env_file() -> None:
    print(f"[1] .env 위치: {ENV_PATH}")
    if not ENV_PATH.exists():
        print("    없음. .env.example을 복사해 이 위치에 .env로 만드세요.")
        for p in PROJECT_DIR.glob(".env*"):
            if p.name != ".env.example":
                print(f"    비슷한 파일 발견: {p.name} (메모장이 .env.txt로 저장했을 수 있습니다)")
        return
    lines = [ln for ln in ENV_PATH.read_text(encoding="utf-8-sig").splitlines()
             if ln.strip().startswith("ANTHROPIC_API_KEY")]
    if not lines:
        print("    ANTHROPIC_API_KEY 줄이 없습니다.")
        return
    if len(lines) > 1:
        print(f"    ANTHROPIC_API_KEY 줄이 {len(lines)}개입니다. 하나만 남기세요.")
    raw = lines[-1].split("=", 1)[1] if "=" in lines[-1] else ""
    if raw != raw.strip():
        print("    값 앞뒤에 공백이 있습니다.")
    if raw.strip()[:1] in "\"'(<" and raw.strip():
        print("    값이 따옴표나 괄호로 감싸져 있습니다. ANTHROPIC_API_KEY=sk-ant-... 형태로 값만 넣으세요.")


def check_loaded_key() -> bool:
    shell_value = os.environ.get("ANTHROPIC_API_KEY")
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    print("[2] 앱이 읽게 될 키")
    if shell_value is not None:
        print("    주의: 터미널(시스템) 환경변수에 ANTHROPIC_API_KEY가 이미 있어 .env 값이 무시됩니다.")
        print("    PowerShell: Remove-Item Env:ANTHROPIC_API_KEY  /  시스템 환경변수에서도 지우세요.")
    if not key:
        print("    비어 있음 → 앱은 모의(mock) 모드로 돕니다.")
        return False
    looks_ok = key.startswith("sk-ant-api") and key.strip() == key
    print(f"    길이 {len(key)}자, 형식 {'정상(sk-ant-api...)' if looks_ok else '이상함 - 복사가 잘렸거나 다른 값'}")
    if not key.startswith("sk-ant-") and not os.environ.get("ANTHROPIC_BASE_URL"):
        print("    Anthropic 발급 키가 아닙니다. 중계(게이트웨이) 키라면 발급처의 접속 주소를 ANTHROPIC_BASE_URL에 넣어야 합니다.")
    provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if provider == "mock":
        print("    LLM_PROVIDER=mock 이라 키가 있어도 모의 모드입니다. 비우거나 anthropic으로 바꾸세요.")
    return True


def call(label: str, fn) -> None:
    import anthropic

    try:
        fn()
        print(f"    {label}: 성공")
    except anthropic.AuthenticationError as e:
        print(f"    {label}: 401 인증 실패 - 키가 틀렸거나 삭제·비활성화됨 ({e.message})")
    except anthropic.PermissionDeniedError as e:
        print(f"    {label}: 403 권한 없음 - 이 키의 워크스페이스에서 모델을 쓸 수 없음 ({e.message})")
    except anthropic.NotFoundError as e:
        print(f"    {label}: 404 모델 없음 - 모델 이름 확인 ({e.message})")
    except anthropic.RateLimitError as e:
        print(f"    {label}: 429 사용량 한도 초과 ({e.message})")
    except anthropic.BadRequestError as e:
        hint = " - 크레딧 잔액 부족" if "credit" in str(e.message).lower() else ""
        print(f"    {label}: 400 잘못된 요청{hint} ({e.message})")
    except anthropic.APIStatusError as e:
        print(f"    {label}: {e.status_code} 서버 오류 ({e.message})")
    except anthropic.APIConnectionError as e:
        print(f"    {label}: 네트워크 연결 실패 - 방화벽·프록시·인증서 문제 ({e.__cause__ or e})")


def check_api() -> None:
    import anthropic

    from app.config import get_settings
    from app.services.agent import llm

    settings = get_settings()
    client = anthropic.Anthropic(timeout=30.0, max_retries=0)
    print(f"[3] 실제 호출 (anthropic {anthropic.__version__}, 접속 주소 {client.base_url})")
    call(f"경량 모델 {settings.fast_model}", lambda: client.messages.create(
        model=settings.fast_model, max_tokens=8,
        messages=[{"role": "user", "content": "ping"}],
    ))
    params = {"model": settings.coach_model, "max_tokens": 256,
              "messages": [{"role": "user", "content": "ping"}],
              "output_config": {"effort": "low"}}
    if llm.use_fallback(settings.coach_model):
        call(f"코치 모델 {settings.coach_model}", lambda: client.beta.messages.create(
            betas=[llm.FALLBACK_BETA], fallbacks="default", **params))
    else:
        call(f"코치 모델 {settings.coach_model}", lambda: client.messages.create(**params))


if __name__ == "__main__":
    sys.path.insert(0, str(PROJECT_DIR))
    check_env_file()
    if check_loaded_key():
        check_api()
