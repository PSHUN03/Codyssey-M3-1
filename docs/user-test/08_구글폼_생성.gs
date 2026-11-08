/**
 * 사다리 사용자 테스트 설문을 구글 폼으로 만든다.
 *
 * 사용법: https://script.google.com 새 프로젝트에 붙여 넣고 실행한다. 처음 실행할 때 구글 계정 권한 승인이 필요하다.
 * - createSadariSurvey: 새 폼을 만든다.
 * - rebuildSadariSurvey: FORM_ID 폼의 문항을 모두 지우고 다시 만든다 (응답 링크 유지).
 * 실행 기록(로그)에 응답용 링크와 편집 링크가 나온다.
 *
 * 문항 제목은 'B1.'처럼 코드로 시작해야 scripts/user_test_summary.py 가 읽을 수 있다.
 * 문항 설명은 docs/user-test/03_설문지.md 와 같다.
 */
var FORM_ID = ''; // 다시 만들 폼의 ID (편집 링크의 /d/ 와 /edit 사이)

function createSadariSurvey() {
  var form = FormApp.create('사다리 사용자 테스트 설문');
  buildSurvey(form);
}

function rebuildSadariSurvey() {
  var form = FormApp.openById(FORM_ID);
  form.getItems().forEach(function (item) { form.deleteItem(item); });
  buildSurvey(form);
}

function buildSurvey(form) {
  form.setTitle('사다리 사용자 테스트 설문');
  form.setDescription(
    '사다리는 첫 월급을 받은 사회초년생이 월급을 어떻게 나눌지, 받을 수 있는 청년 혜택이 무엇인지 확인하고 ' +
    'AI 코치와 함께 계획을 지켜 가도록 돕는 서비스입니다.\n' +
    '사다리를 써 보신 뒤 답해 주세요. 5분 정도 걸리며, 이름·연락처·이메일은 받지 않습니다.'
  );
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setLimitOneResponsePerUser(false);
  form.setProgressBar(true);
  form.setConfirmationMessage('응답해 주셔서 고맙습니다. 남겨 주신 의견은 사다리를 고치는 데 쓰겠습니다.');

  // 1. 동의
  form.addSectionHeaderItem().setTitle('1. 응답 활용 동의');
  form.addCheckboxItem()
    .setTitle('P1. 이 설문의 응답은 이름이나 연락처 없이 저장되며, 사다리 개선과 코디세이 프로젝트 발표에 통계와 익명 인용으로만 쓰입니다. 응답은 2026년 12월 31일에 삭제합니다. 동의하십니까?')
    .setChoiceValues(['동의합니다'])
    .setRequired(true);

  // 2. 응답자 정보
  form.addPageBreakItem().setTitle('2. 응답자 정보')
    .setHelpText('사다리가 주로 돕고자 하는 사람(첫 월급을 받은 지 얼마 안 된 사회초년생)과 얼마나 가까운지 보기 위한 질문입니다.');
  choice(form, 'A1. 나이대', ['10대', '20대', '30대', '40대', '50대', '60대 이상'], true);
  choice(form, 'A2. 지금 하고 있는 일', ['학생', '취업 준비 중', '직장인(정규직)', '직장인(계약직·인턴)', '프리랜서·자영업', '아르바이트', '기타'], true);
  choice(form, 'A3. 첫 월급(일해서 처음 번 소득)을 받은 지 얼마나 됐나요?', ['아직 받은 적 없음', '1년 미만', '1~3년', '3~5년', '5년 이상'], true);
  form.addCheckboxItem()
    .setTitle('A4. 지금 돈 관리는 어떻게 하고 있나요? (모두 선택)')
    .setChoiceValues(['가계부 앱', '은행·카드 앱에서 내역만 확인', '엑셀이나 메모', '따로 관리하지 않음'])
    .showOtherOption(true)
    .setRequired(true);
  choice(form, 'A5. 청년미래적금, 청년월세 지원 같은 청년 금융 혜택을 신청해 본 적이 있나요?', ['신청해 봤다', '알고는 있지만 신청하지 않았다', '잘 모른다'], true);
  choice(form, 'A6. 사다리를 어떻게 써 봤나요?', ['직접 가입해 내 실제 정보로', '직접 가입했지만 지어낸 정보로', '예시 계정(가상 인물 지우)으로 둘러봄'], true);

  // 3. 사용한 기능
  form.addPageBreakItem().setTitle('3. 사용한 기능');
  form.addCheckboxItem()
    .setTitle('U1. 써 본 기능을 모두 골라 주세요.')
    .setChoiceValues(FEATURES)
    .setRequired(true);
  choice(form, 'U2. 재무 진단(질문 카드)을 끝내는 데 걸린 시간', ['3분 이내', '3~5분', '5~10분', '10분 넘게', '끝내지 못함', '진단을 하지 않음(예시 계정 등)'], true);
  choice(form, 'U3. 가장 도움이 된 기능 하나를 골라 주세요.', FEATURES.concat(['도움이 된 기능이 없음']), true);

  // 4. 사용성 (SUS 10문항, 홀수는 긍정·짝수는 부정 문장)
  form.addPageBreakItem().setTitle('4. 사용 편의성')
    .setHelpText('사다리 전체를 써 본 느낌으로 답해 주세요. 1=전혀 아니다, 5=매우 그렇다');
  var sus = [
    '사다리를 자주 쓰고 싶다.',
    '사다리는 필요 이상으로 복잡하다.',
    '사다리는 쓰기 쉬웠다.',
    '사다리를 쓰려면 다른 사람의 도움이 필요할 것 같다.',
    '진단, 플랜, 혜택, 코치 기능이 자연스럽게 이어졌다.',
    '화면마다 쓰는 방식이 달라 헷갈리는 부분이 많았다.',
    '대부분의 사람이 사다리 사용법을 금방 익힐 것 같다.',
    '사다리는 쓰기 번거로웠다.',
    '사다리를 쓰는 동안 다음에 무엇을 하면 되는지 알고 썼다.',
    '사다리를 쓰기 전에 따로 익혀야 할 것이 많았다.'
  ];
  for (var i = 0; i < sus.length; i++) {
    scale(form, 'B' + (i + 1) + '. ' + sus[i], 1, 5, '전혀 아니다', '매우 그렇다', true);
  }

  // 5. 기능별 평가
  form.addPageBreakItem().setTitle('5. 기능별 평가')
    .setHelpText('1=전혀 아니다, 5=매우 그렇다. 써 보지 않은 기능의 문항은 비워 두세요.');
  var items = [
    'C1. 재무 진단 질문이 무엇을 묻는지 이해하기 쉬웠다.',
    'C2. 월급 배분 플랜에서 각 금액이 왜 그렇게 나뉘었는지 이해할 수 있었다.',
    'C3. 월급 배분 플랜이 내 실제 생활(고정비, 생활비, 저축)에 맞았다.',
    'C4. 청년 혜택마다 내가 받을 수 있는지와 그 이유가 분명하게 나왔다.',
    'C5. AI 코치의 답변이 내 소득과 지출 상황을 반영했다.',
    'C6. AI 코치가 알려 준 금액과 정보를 믿을 수 있었다.',
    'C7. AI가 만든 답변이라는 표시와 한계 안내를 알아볼 수 있었다.',
    'C8. 사다리에 내 재무 정보를 입력하는 것이 부담스럽지 않았다.',
    'C9. 사다리를 쓰고 나서 이번 달에 해 볼 구체적인 행동(저축액 조정, 혜택 신청 등)이 생겼다.'
  ];
  for (var j = 0; j < items.length; j++) {
    scale(form, items[j], 1, 5, '전혀 아니다', '매우 그렇다', false);
  }

  // 6. 혜택 발견
  form.addPageBreakItem().setTitle('6. 청년 혜택');
  choice(form, 'D1. 사다리에서 처음 알게 된 청년 혜택은 몇 개인가요?', ['0개', '1개', '2개', '3개 이상'], true);
  form.addParagraphTextItem().setTitle('D2. 신청하거나 더 알아볼 생각이 생긴 혜택이 있다면 적어 주세요.').setRequired(false);

  // 7. 전체 평가와 의견
  form.addPageBreakItem().setTitle('7. 전체 평가와 의견');
  choice(form, 'E1. 다음 월급을 받았을 때도 사다리로 배분을 확인하거나 코치에게 물어볼 생각이 있나요?', ['예', '아마도', '아니요'], true);
  scale(form, 'E2. 친구나 동료에게 사다리를 추천할 가능성은 얼마나 되나요?', 0, 10, '전혀 추천하지 않음', '꼭 추천함', true);
  form.addParagraphTextItem().setTitle('E3. 가장 좋았던 점은 무엇인가요? (어느 기능에서 어떤 점이 좋았는지)').setRequired(false);
  form.addParagraphTextItem().setTitle('E4. 헷갈리거나 불편했던 점은 무엇인가요? (어느 화면에서 무엇이 그랬는지)').setRequired(false);
  form.addParagraphTextItem().setTitle('E5. 무엇이 바뀌거나 추가되면 사다리를 계속 쓰시겠어요?').setRequired(false);

  Logger.log('응답용 링크: ' + form.getPublishedUrl());
  Logger.log('편집 링크: ' + form.getEditUrl());
}

var FEATURES = [
  '재무 진단(질문 카드)',
  '월급 배분 플랜',
  '청년 혜택 찾기와 자격 확인',
  'AI 코치 상담',
  '코치가 기억하는 내용(설정)',
  '로그인 없이 쓰는 월급 계산기'
];

function choice(form, title, values, required) {
  return form.addMultipleChoiceItem().setTitle(title).setChoiceValues(values).setRequired(required);
}

function scale(form, title, low, high, lowLabel, highLabel, required) {
  return form.addScaleItem().setTitle(title).setBounds(low, high).setLabels(lowLabel, highLabel).setRequired(required);
}
