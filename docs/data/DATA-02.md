# DATA-02 정책 자동 갱신

라우터와 자동 갱신을 실제 코드에 연결했습니다. APP_WIRING.patch는 사용하지 않습니다.

- YOUTHCENTER_API_KEY와 INTERNAL_API_KEY를 서버 환경에만 설정합니다.
- POLICY_EXTERNAL_FILE은 영속 디스크 경로를 사용합니다. 검수된 시드와 외부 수집 자료를 분리하며 실패 시 기존 자료를 보존합니다. 단일 앱 프로세스 전제이며 여러 worker는 DB/캐시 설계가 추가로 필요합니다.
- n8n/policy_refresh.json은 비활성입니다. 매일 03:00 Asia/Seoul, ingest 후 변경 건수만 Discord에 알립니다.
- n8n의 SADARI_BASE_URL 변수와 X-Internal-Key Header Auth 자격 증명을 설정합니다. Discord 웹훅은 공개 변수·저장소에 기록하지 말고 인스턴스 비밀 저장 방식을 사용합니다.
- 실제 API 키·응답, n8n import·예약·Discord 발송은 미검증입니다. 자동 수집 정책은 자격을 확정하지 않습니다.
