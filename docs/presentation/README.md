# 발표 자료

| 파일 | 설명 |
|---|---|
| `sadari_presentation.pptx` | 발표 자료 초안 (17장, 16:9, Paperlogy 폰트 포함, 슬라이드마다 발표자 노트) |
| `sadari_presentation.pdf` | 백업용 PDF (발표 PC 문제에 대비) |
| `screens/` | 앱 화면 캡처 5장 (모의 AI 모드, 예시 계정 '지우'와 진단 화면) |
| `capture_screens.py` | 휴대폰 화면 캡처 (750×1624, headless Chrome, Playwright 필요) |
| `build_deck.py`, `finalize_deck.ps1` | 초안 생성 스크립트 (구조를 크게 바꿀 때만 사용) |
| [예상질문.md](예상질문.md) | 질의응답 예상 질문 10개, 답변 초안과 답변자 |

## 구성 (발표 10분 + 질의응답 10분)

| # | 슬라이드 | 채울 것 |
|---|---|---|
| 1 | 표지 | 팀명·팀장명, 워드마크 서체 (심볼은 A안으로 확정) |
| 2~4 | 문제 정의: 자산 격차 40배, 금융이해력 차트, 페인포인트 4 | |
| 5~7 | 해결: 기존 서비스 비교, 5단계 흐름(페르소나 지우), 실제 화면 5장 | 실제 AI 연결 후 `capture_screens.py`로 다시 캡처 |
| 8~12 | AI 설계: 쓰는 곳/안 쓰는 곳, Agent 구조, RAG, 안전장치·품질 지표 | 평가셋 확장 후 지표 갱신 |
| 13 | 구현: 아키텍처와 ADR 8건 | |
| 14 | 협업: 역할 5개, 이슈 26개, 작업 흐름 | 담당자 이름 |
| 15 | 사용자 테스트 결과 | **테스트 후 전부 입력** |
| 16 | 기대효과·비즈니스 모델 | |
| 17 | 마무리·Q&A | 배포 URL, 저장소 주소 |

## 수정 방법

- **PowerPoint에서 바로 고치세요.** 사용자 테스트 결과, 이름, URL처럼 내용을 채우는 작업은 스크립트를 다시 돌릴 필요가 없습니다.
- 폰트가 파일에 포함되어 있어 Paperlogy가 없는 PC에서도 보기는 문제없습니다. **편집하는 사람은 Paperlogy를 설치**하는 것이 좋습니다 (새로 입력한 글자가 다른 폰트로 바뀌는 것을 막기 위해).
- 디자인 규칙: 16:9, 모든 글자는 Paperlogy, 챕터 라벨·제목·부제는 모든 슬라이드에서 같은 위치, 파란색(#0075DE)은 버튼·링크·챕터 라벨에만, 슬라이드 아래쪽이 비지 않게 구성.

## 스크립트로 다시 만들기 (Windows + PowerPoint)

```bash
python docs/presentation/capture_screens.py   # 서버 실행 중일 때
python docs/presentation/build_deck.py
powershell -ExecutionPolicy Bypass -File docs/presentation/finalize_deck.ps1 -FontDir <Paperlogy ttf 폴더>
```

`finalize_deck.ps1`은 Paperlogy 폰트를 이번 실행 동안만 임시로 등록해 PowerPoint로 폰트를 포함해 저장한 뒤 등록을 해제합니다. 스크립트로 다시 만들면 PowerPoint에서 직접 고친 내용은 사라지니 주의하세요.
