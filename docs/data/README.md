# RAG·데이터 담당 개발본

이 폴더의 안내는 2026-10-31 로컬 검증 기준입니다. 기존 MVP 원작성자는 @PSHUN03 및 Claude Code입니다. 이번 기능 추가는 Codex로 작성·검증했습니다. 사용자가 직접 검토·설명하거나 GitHub에서 리뷰한 기록은 아직 아닙니다.

## 준비된 것과 남은 것

| 이슈 | 로컬 준비 상태 | 남은 일 |
|---|---|---|
| MIG-2 | #43 승인·병합 완료 | 없음 (원본 이관 범위) |
| DATA-01 | #44: 20개 정책, 추가 13개 중 주요 항목 대조 10개·부분 확인 3개 | 기존 7개 예외·부분 확인 3개 최종 검수 |
| DATA-06 | CSV/XLSX 변환·마스킹·분류, API 라우터와 모의 3종 검증 | 실제 비식별 은행 양식·실제 LLM, BE 저장·FE 연결 |
| DATA-02 | API 수집·파일 교체·검색 캐시 초기화, 비활성 n8n JSON | 실제 키·응답, 영속 디스크, n8n import/실행 |
| DATA-03 | 공시 조회·하루 캐시·기간별 기본금리 비교 | 실제 키·응답, 코치·화면 연결 패치 적용 |
| DATA-04 | 리포트 생성·저장·선점·동의 재확인, n8n JSON | 실제 납입 기록·LLM 선택 연결, 호스팅·Gmail 실행 |
| DATA-05 | 기존 12문항 평가와 개발용 40문항 초안 | PM 독립 골든셋 40문항 및 최종 평가 |

## 이번 PR의 연결 범위

팀 main에는 MIG-3~5 이관이 아직 모두 반영되지 않은 상태에서 준비했습니다. 다른 팀원의 전체 원본을 이번 기여로 복사하지 않았습니다. 서비스와 내부 API는 직접 검증하고, 화면·코치 도구·앱 라우터 연결 변경은 `docs/data/APP_WIRING.patch`로 제공합니다.

MIG-3~5 이관 후 백엔드·AI·FE 담당자가 변경을 확인하고 프로젝트 루트에서 `git apply --check docs/data/APP_WIRING.patch`, 이어서 `git apply docs/data/APP_WIRING.patch`로 연결합니다. 팀에서 해당 파일을 수정했다면 그대로 강제 적용하지 말고 패치의 변경 부분만 최신 코드에 맞춰 반영합니다. 패치는 전체 원본 MVP 기준 적용 및 통합 테스트를 완료했습니다.

새 라우터는 `data.create_router(require_onboarded)`로 생성합니다. 앱의 실제 로그인·동의·진단 의존성을 반드시 전달해야 하며 인증을 생략한 기본 라우터는 제공하지 않습니다. 설치·실행은 전체 이관과 연결 이후 가능합니다.

검증: 담당 브랜치 pytest 106개, 전체 MVP+연결 패치 pytest 141개, 양쪽 Ruff 통과. 이 검증에 실제 외부 API 호출·Claude 호출·메일 발송은 포함하지 않았습니다.

## 설치와 실행

Python 3.12 이상이 필요합니다. 아래 명령은 프로젝트 폴더에서 실행합니다.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

`.env`의 `LLM_PROVIDER=mock`을 유지하면 Claude 키 없이 화면과 테스트를 사용할 수 있습니다. 외부 데이터 키가 없을 때 금리를 지어내거나 실제 수집에 성공한 것처럼 응답하지 않습니다.

```sh
python -m pytest -q
ruff check .
python eval/run_policy_eval.py
python eval/run_policy_eval.py --dataset eval/golden_policy_qa.jsonl
uvicorn app.main:app --reload
```

브라우저에서 `http://localhost:8000`의 **예시 계정으로 둘러보기**를 선택합니다. 새 API는 `http://localhost:8000/api/docs`에서도 확인할 수 있습니다.

## 백엔드·프론트와 합의할 입출력

- `parse_transactions(content: bytes, filename: str, mapping=None, header_row=None, structured_call=None)`
- 결과 `transactions`: `date`(YYYY-MM-DD), `amount`(원, 출금 음수·입금 양수), `merchant`(가림 처리), `category`.
- `needs_mapping=true`이면 가린 앞 20행 `preview`를 이용해 수동 열 매핑. `mapping={"date":0,"merchant":1,"withdrawal":2,"deposit":3}`처럼 0부터 시작하는 열 번호 사용.
- 오류는 행 번호와 일반 사유만 반환하며 원본을 오류 메시지에 넣지 않음. 합계/잔액 열은 거래금액으로 쓰지 않음.
- 업로드 API: `POST /api/transactions/preview`, multipart `file`, 선택 `mapping` JSON 문자열, `header_row`. 로그인·동의·진단 필요. 2MB, CSV/XLSX, 10,000건·100열 제한.
- 미리보기 결과는 아직 DB에 저장하지 않음. 저장·분류 수정·월별 소비 요약은 BE-01/FE-02 담당과 연결 필요.
- 거래내역에서 가맹점 외 자유 기재란에는 사람 이름이 들어갈 수 있음. 실제 LLM 연결 전 팀과 허용 필드/추가 비식별 규칙 확인. 전체 거래내역은 외부 LLM에 보내지 않음.
- 모의 CSV/XLSX 3개는 `tests/fixtures/transactions/`에 있음. 은행 공식 실제 양식 검증을 대신하지 않음.
- `GET /api/products/compare?term_months=12&product_type=savings` (`deposit`도 가능).
- `compare_savings_products` 코치 도구를 추가했으며 입력은 `term_months`, `product_type`.
- 기본금리 기준 상품별 상위 5개. 기본/최고금리·우대조건·공시월·수집일 반환. 은행권(020000) 범위이며 개인별 가입 가능 순위가 아님.
- `GET /api/reports/weekly`: 로그인 사용자 자신의 최근 리포트만 반환. 비동의 사용자는 이메일 없이 홈에서 확인.

## 내부 자동화 API

모든 내부 API에 `X-Internal-Key`가 필요합니다. 키가 비어 있으면 허용하지 않습니다.

| 메서드·경로 | 기능 |
|---|---|
| POST /internal/policies/ingest | 키로 온통청년을 수집하고 변환·저장. 클라이언트가 임의 정책을 주입하지 않음 |
| POST /internal/reports/weekly | 최근 30일 활동·진단 완료 회원의 리포트 생성, 발송 대기 ID만 반환 |
| POST /internal/reports/{id}/claim | 최신 이메일 동의 재확인 후 한 worker만 발송 건 선점 |
| POST /internal/reports/{id}/complete | claim_token을 검증하고 발송 완료 기록 |

주간 활동은 현재 스키마에서 확인 가능한 프로필 수정·대화 시점을 사용합니다. 정확한 최근 로그인 기록은 BE 연동이 필요합니다. 같은 사용자·주차에는 하나의 리포트만 생성합니다. 실제 적금 납입 기록이 없어 납입 위험·진척률을 추측하지 않습니다. 현재 요약은 규칙 기반이며 AI가 작성했다고 표시하지 않습니다.

이메일은 선점 후 자동 재시도하지 않습니다. Gmail 발송 이후 완료 API가 실패하거나 선점 후 worker가 종료된 경우 `claimed` 상태로 남습니다. 중복 발송을 피하기 위한 선택이며 운영자가 Gmail 발송 이력을 확인해 수동 처리해야 합니다. 이는 정확히 한 번 전달 보장이 아닙니다.

## 운영 연결

1. 온통청년 `YOUTHCENTER_API_KEY`, 금감원 `FSS_API_KEY`, 내부 `INTERNAL_API_KEY`를 서버 환경에 설정.
2. `POLICY_EXTERNAL_FILE`을 Render 영속 디스크 경로로 설정. 자동 수집 파일은 검수한 정책 시드와 별개입니다. 임시 디스크에 두면 재배포 때 사라집니다.
3. 현재 정책 캐시는 단일 앱 프로세스를 전제로 합니다. 여러 worker/인스턴스는 DB 저장소와 캐시 무효화 전달이 필요합니다.
4. n8n 연결은 `n8n/SETUP.md` 참조. JSON 구조만 로컬 검증했고 n8n에서 import/실행하지 않았습니다.
5. 실제 호출 검증 전에는 배포/메일/실시간 API 연동 완료로 보고하지 않습니다.
