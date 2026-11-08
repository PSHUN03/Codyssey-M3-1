# DATA-06 거래 변환 계약

CSV/XLSX, UTF-8/CP949, 최대 2MB·10,000거래. 날짜 YYYY-MM-DD, 금액 정수 원(출금 음수/입금 양수), 가맹점 가림 처리, 분류 10종.

POST /api/transactions/preview: 로그인·동의·진단 완료 필요. multipart file, 선택 mapping JSON 및 header_row(모두 열·행 번호는 0부터). needs_mapping=true이면 preview를 이용해 매핑을 선택합니다. errors.row는 원본의 1부터 시작하는 행 번호입니다. 미리보기는 저장하지 않으며 BE 저장 API와 별도 연결합니다. 예시 JSON은 transactions-example.json 및 이슈 #15에 있습니다. 모의 은행 양식 3종을 검증했으며 실제 양식·실제 LLM 검증은 남았습니다.
