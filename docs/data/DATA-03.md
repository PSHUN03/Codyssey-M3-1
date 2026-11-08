# DATA-03 공시 금리 비교

GET /api/products/compare?term_months=12&product_type=savings 또는 deposit. 로그인·동의·진단 필요. 금감원 은행권 공시의 기본금리 순 상위 5개를 반환하며 기본금리·최고 우대금리·조건·기준일을 구분합니다. 코치 도구와 프롬프트에 직접 연결했고 가입 권유로 표현하지 않습니다.

실제 FSS_API_KEY는 서버 환경에만 설정합니다. 키 없이 금리를 생성하지 않습니다. 하루 파일 캐시는 단일 프로세스 기준이며 app/data/cache는 영속 디스크 운영을 검토해야 합니다. 실제 키·API 응답·Claude 호출은 미검증입니다.
