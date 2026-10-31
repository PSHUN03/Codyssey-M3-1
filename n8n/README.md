# n8n 자동화 워크플로우 설계

과제 목표 4번 "노코드 자동화 도구와 Python을 조합하여 서비스를 구축한 경험"에 대응합니다.
**n8n은 흐름(언제·어디로)을 맡고, 판단과 계산은 사다리 Python API가 맡습니다.**

워크플로우를 만들면 n8n에서 **Download(JSON 내보내기)** 한 파일을 이 폴더에 커밋하세요. 내보낸 JSON에 비밀값(자격 증명)이 들어가지 않았는지 커밋 전에 확인합니다.

## 공통: 사다리 내부 API 호출

- 모든 요청 헤더: `X-Internal-Key: <INTERNAL_API_KEY>` (n8n의 Credentials → Header Auth로 저장)
- 연결 확인: `GET /internal/ping` → `{"ok": true}`

## W1. 정책 데이터 자동 갱신 (FR-18, 담당 DATA-02)

```
Schedule Trigger (매일 04:00 KST)
  → HTTP Request: POST /internal/policies/ingest
  → IF 변경 건수 > 0
      → Discord: "정책 N건 추가·변경 (목록)"
```

## W2. 주간 체크인 (FR-15, 담당 DATA-04)

```
Schedule Trigger (매주 일요일 20:00 KST)
  → HTTP Request: POST /internal/reports/weekly      ← 대상 사용자와 리포트 본문을 받는다
  → Split Out (사용자별)
  → IF 이메일 수신 동의(weekly_email) = true
      → Gmail/SMTP: 리포트 발송 (제목: "[사다리] 이번 주 체크인")
  → 발송 결과 집계 → Discord 알림
```

- 리포트의 금액은 API가 계산한 값만 쓴다 (n8n이나 LLM 노드에서 새로 계산하지 않는다).
- 이메일 본문 하단에 'AI 생성' 표시와 수신 거부 방법(설정 → 동의 변경)을 넣는다.

## W3. 피드백 → GitHub Issue (FR-17, 담당 PM-02)

```
Webhook (POST /webhook/sadari-feedback)
  → Set: 제목 "[피드백] {의견 앞 30자}", 본문(질문·답변·의견·날짜), 라벨 user-feedback
  → GitHub: Create Issue
  → Discord: 새 피드백 알림
```

- 사다리 서버는 '아쉬워요'(rating -1) 피드백일 때만 이 웹훅을 호출한다 (`FEEDBACK_WEBHOOK_URL`).
- 이메일·닉네임 같은 개인정보는 보내지 않는다.

## 호스팅 선택지 (DATA-04에서 결정 후 ADR 작성)

| 선택지 | 비용 | 장단점 |
|---|---|---|
| n8n Cloud 체험판 | 무료(체험 기간) | 설정이 가장 쉬움, 체험 기간이 끝나면 유료 |
| 팀원 PC에서 실행 (`npx n8n` 또는 데스크톱 앱) | 무료 | 발표 기간에 PC를 켜둬야 함, 웹훅은 터널(ngrok 등) 필요 |
| Render 무료 웹 서비스 (Docker `n8nio/n8n`) | 무료 | 15분 유휴 시 잠들어 예약 실행이 누락될 수 있음 |

예약 실행이 누락되면 안 되는 W2는, n8n이 잠들 수 있는 환경이라면 Render Cron Job에서 같은 API를 호출하는 방식으로 보완할 수 있습니다.
