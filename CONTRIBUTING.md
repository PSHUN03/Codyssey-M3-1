# 협업 규칙

평가에서 '팀 구성 및 협업'이 30점입니다. 평가표는 "특정 팀원에게 개발 부담이 몰리지 않고 모든 팀원이 균형 있게 기여했는지"와 "Git 커밋 로그, 이슈, 코드 리뷰 기록으로 상호 검토를 증빙할 수 있는지"를 봅니다. 아래 규칙을 지키면 각자의 기여가 GitHub에 자연스럽게 증빙으로 남습니다.

## 0. 처음 참여할 때

1. **초대 수락**: 저장소 협업자 초대 메일(또는 GitHub 알림)에서 수락합니다.
2. **이메일 비공개 설정**: 공개 저장소라 커밋에 적힌 이메일이 누구에게나 보입니다. GitHub → Settings → Emails에서 "Keep my email addresses private"와 "Block command line pushes that expose my email"을 켜고, 그 화면에 나오는 `숫자+아이디@users.noreply.github.com` 주소를 복사합니다.
3. **내려받기와 git 설정**

   ```bash
   git clone https://github.com/PSHUN03/Codyssey-M3-1.git
   cd Codyssey-M3-1
   git config user.name "GitHub아이디"
   git config user.email "숫자+아이디@users.noreply.github.com"
   ```

4. **로컬 실행**: [README의 실행 방법](README.md#실행-방법)대로 가상환경을 만들고 `pytest -q`가 통과하는지 확인합니다. API 키가 없어도 모의 AI 모드로 전부 동작합니다.
5. **첫 PR은 이관 PR**: 기존 MVP 코드 중 자기 담당 모듈을 읽고 테스트한 뒤 PR로 옮깁니다. 절차와 순서는 [이관 안내](docs/migration.md)에 있습니다. 아래 작업 흐름을 그대로 한 번 연습하게 됩니다.

## 1. 작업 흐름 (GitHub Flow)

1. **이슈 먼저**: 모든 작업은 이슈에서 시작합니다. 역할별 이슈는 [docs/tasks](docs/tasks)에서 등록했고, 새 작업은 이슈 템플릿으로 만듭니다. 시작할 때 이슈를 칸반의 In Progress로 옮깁니다.
2. **브랜치**: 최신 `main`에서 `종류/이슈ID-짧은설명`으로 만듭니다.

   ```bash
   git switch main && git pull
   git switch -c feature/DATA-06-excel-parser
   ```

   | 종류 | 쓰임 |
   |---|---|
   | `feature/` | 새 기능 |
   | `fix/` | 버그 수정 |
   | `docs/` | 문서만 바꿀 때 |
   | `test/` | 테스트·평가셋 |
   | `chore/` | 설정, 의존성 |

3. **커밋**: [Conventional Commits](https://www.conventionalcommits.org/ko/) 형식으로 씁니다. 작게, 자주 커밋합니다. 각자의 커밋이 곧 기여 기록입니다.
   - `feat: 거래내역 엑셀 컬럼 자동 매핑 (#12)`
   - `fix`, `docs`, `test`, `refactor`, `chore`
4. **PR**: 하루 이상 걸리는 작업은 먼저 Draft PR로 올려 진행 상황을 공유합니다. 템플릿을 채우고 본문에 `Closes #이슈번호`를 적습니다. 리뷰어는 아래 리뷰 짝으로 지정합니다.
5. **리뷰와 머지**: 다른 팀원 1명이 승인하고 CI가 통과하면 **PR 작성자가 직접** 머지합니다. 머지 방식은 "Create a merge commit"을 씁니다. 각자의 커밋이 `main` 기록에 그대로 남습니다.
6. **머지 후**: 이슈가 자동으로 닫히는지 확인하고 칸반 카드를 Done으로 옮깁니다. `main`에 머지되면 Render가 자동 배포합니다.

### `main` 보호 규칙

`main`에는 GitHub 규칙([.github/rulesets/main.json](.github/rulesets/main.json))이 걸려 있어 아래를 지키지 않으면 머지가 막힙니다. 팀장을 포함해 예외는 없습니다.

- `main`에 직접 push 금지. 모든 변경은 PR로
- 다른 팀원 1명 이상의 승인. 승인 후 새 커밋을 올리면 다시 승인을 받습니다
- CI(`test`: ruff, pytest, AI 품질 평가) 통과
- 강제 push(`--force`)와 브랜치 삭제 금지

## 2. 코드 리뷰 짝

| 작성자 | 1차 리뷰어 | 이유 |
|---|---|---|
| 프론트엔드 @hyoryeomii | 백엔드 @1yuxnp | 화면과 API 계약 확인 |
| 백엔드 @1yuxnp | 프론트엔드 @hyoryeomii | API 사용성 확인 |
| AI Agent @zero-ysyang | RAG·데이터 @yak7297 | AI 품질 교차 검토 |
| RAG·데이터 @yak7297 | AI Agent @zero-ysyang | 검색·도구 연동 확인 |
| PM @PSHUN03 | 아무나 1명 | 문서·QA 결과 확인 |

리뷰 댓글은 "왜"를 함께 씁니다. 승인만 누르지 말고 읽은 내용과 확인한 것을 한 줄이라도 남깁니다. 리뷰 기록이 동료 학습의 증빙이 됩니다.

## 3. 완료 기준 (Definition of Done)

- [ ] `pytest -q`, `ruff check .` 통과 (CI가 PR마다 자동 실행)
- [ ] 새 기능에는 테스트를 추가
- [ ] 배포 환경에서 동작 확인
- [ ] 관련 문서(요구사항정의서, README, ADR) 갱신

## 4. AI 코딩 도구 사용 원칙

- AI가 만든 코드도 **사람이 읽고 이해한 뒤** 커밋합니다. 설명하지 못하는 코드는 머지하지 않습니다. 발표 질의응답에서 직접 설명해야 합니다.
- PR 본문에 AI 도구를 어디에 썼는지, 무엇을 직접 고쳤는지 적습니다.
- 비밀값(API 키 등)과 개인정보를 AI 도구나 코드에 붙여넣지 않습니다.

## 5. 회의와 기록

| 회의 | 시간 | 기록 위치 |
|---|---|---|
| 스탠드업 | 화·금 15분 (디스코드) | `docs/meetings/YYYY-MM-DD.md` |
| 주간 회고·계획 | 일요일 30분 | `docs/meetings/YYYY-MM-DD.md` |
| 멘토링 | 2주 1회 | `docs/meetings/YYYY-MM-DD-mentoring.md` |

- 회의록도 PR로 올리면 누가 기록했는지 남습니다. 돌아가며 작성합니다.
- 기술 결정은 `docs/adr/`에 ADR로 남깁니다 (템플릿: `docs/adr/0000-template.md`).
- 개발 중 배운 점·문제 해결 과정은 `docs/devlog/`에 남깁니다. 발표 자료의 재료가 됩니다.

## 6. 비밀값과 개인정보

공개 저장소이므로 커밋, 이슈, PR, 댓글 어디에도 아래를 올리지 않습니다.

- **비밀값**: API 키, 토큰, 비밀번호, 실제 값이 든 `.env`와 DB 접속 주소. 필요한 변수는 `.env.example`에 이름만 적고, 운영 비밀값은 Render 대시보드에만 저장합니다.
- **개인정보**: 실명, 개인 이메일, 전화번호, 실제 거래내역·영수증 원본, 테스터 응답 원본. 사람은 GitHub 아이디로, 테스터는 T-01처럼 번호로 적습니다. 테스트용 파일은 가짜 데이터로 만듭니다.
- **실명이 필요한 제출용 파일**(기획서 등)은 `private/` 폴더에서 만듭니다. 이 폴더는 `.gitignore`로 제외되어 올라가지 않습니다.
- `git add .` 대신 바꾼 파일을 골라서 추가하고, 커밋 전에 `git diff --cached`로 한 번 확인합니다.
- 실수로 올렸다면 지우는 커밋만으로는 기록에 남습니다. 즉시 팀에 알리고, 키는 폐기·재발급합니다.
