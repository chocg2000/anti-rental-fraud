import { Link } from 'react-router-dom'
import { useJsonLd } from '../lib/seo'

const FRAUD_TYPES = [
  {
    title: '깡통전세 (매매가 대비 보증금 초과)',
    body: '전세 보증금과 선순위채권 합계가 시세 대비 안전 임계값(LTV)을 넘으면, 집이 경매로 넘어갔을 때 보증금을 다 못 돌려받을 수 있습니다.',
    coverage: '국토교통부 실거래가 기준으로 자동 계산합니다.',
  },
  {
    title: '신축빌라 바지사장 명의변경',
    body: '건축주가 세입자를 들인 직후 무자력자에게 명의를 넘기는 패턴입니다. 근저당이 적어도 위험할 수 있습니다.',
    coverage: '건축물대장 사용승인일과 등기부 갑구 소유권 이전 이력을 교차검증해 자동 확인합니다.',
  },
  {
    title: '선순위 근저당 은닉',
    body: '등기부 요약 페이지만 보면 놓치기 쉬운 근저당이 본문(을구)에 남아있는 경우가 있습니다.',
    coverage: '요약 페이지와 을구 본문을 함께 대조해 더 큰 금액을 채택합니다(과소평가 방지).',
  },
  {
    title: '위반건축물 쪼개기(불법 개조)',
    body: '근린생활시설을 주거용으로 쪼개 불법 개조한 건물은 추후 원상복구 명령이나 강제퇴거 위험이 있습니다.',
    coverage: '정부 API가 위반건축물 여부를 공식적으로 공개하지 않아, 자가진단 체크리스트로 확인이 필요합니다(자동 확인 불가 — 정직하게 안내드립니다).',
  },
  {
    title: '대항력 공백 / 동시진행 사기',
    body: '전입신고의 대항력은 익일 0시부터 발생합니다. 잔금일 당일 다른 권리가 접수되면, 그 권리가 먼저 우선순위를 차지합니다.',
    coverage: '등기부 접수일과 잔금(입주)일을 비교해 당일 접수된 권리가 있는지 자동 확인합니다.',
  },
]

const FAQ_ITEMS = [
  {
    q: '등기부 요약 페이지에 근저당이 없으면 무조건 안전한가요?',
    a: '아닙니다. 요약 페이지는 참고용이라 실제 권리관계와 차이가 있을 수 있습니다. 본 서비스는 등기부 본문(을구)까지 함께 확인해, 과거 임차권등기명령 이력이나 오래된 등기의 한글 숫자 표기로 누락되기 쉬운 근저당 금액까지 교차검증합니다.',
  },
  {
    q: '등기부등본 을구의 "말소" 표시는 무슨 뜻인가요?',
    a: '근저당권이나 전세권 같은 권리가 해제·소멸됐다는 뜻입니다. 말소된 권리는 더 이상 유효하지 않으므로 선순위채권 계산에서 제외해야 합니다.',
  },
  {
    q: '주요등기사항요약은 그대로 믿어도 되나요?',
    a: '요약본 자체가 "참고용"이라고 명시하고 있어, 실제 법적 효력은 등기사항전부증명서(등기부 본문)에 있습니다. 계약 직전에는 발급일이 최신인 등기부 전부를 다시 확인하는 것이 안전합니다.',
  },
  {
    q: '전세 보증금이 압류될 수 있는지 확인하는 법은?',
    a: '등기부 갑구에 가압류·압류·경매개시결정 등록 여부를, 을구에 임차권등기명령 이력을 확인하면 됩니다. 본 서비스는 이 항목이 하나라도 발견되면 즉시 \'위험\' 등급으로 표시합니다.',
  },
]

const HOW_TO_STEPS = [
  { name: '주소·계약조건 입력', text: '주소, 전용면적, 보증금, 임대인 이름, 잔금(입주)일을 입력합니다.' },
  { name: '등기부등본 업로드 및 자가진단', text: '등기부등본 PDF를 업로드하고(선택), 위반건축물·완납증명서·확정일자 여부를 확인합니다.' },
  { name: '안전 등급 리포트 확인', text: '안전·주의·경고·위험 4단계 등급과 항목별 판단 근거를 확인합니다.' },
]

const USE_CASES = [
  '원룸·빌라 전세 계약을 앞두고 있다면 — 원룸 전세사기 확인',
  '신축 빌라라 시세 파악이 어렵다면 — 빌라 깡통전세 계산',
  '등기부등본을 받았는데 뭘 봐야 할지 모르겠다면 — 등기부등본 무료 안전 진단',
  '오피스텔 선순위 채권이 얼마인지 궁금하다면 — 오피스텔 선순위 채권 계산',
]

function jsonLdFor(faqItems, howToSteps) {
  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'FAQPage',
        mainEntity: faqItems.map((item) => ({
          '@type': 'Question',
          name: item.q,
          acceptedAnswer: { '@type': 'Answer', text: item.a },
        })),
      },
      {
        '@type': 'HowTo',
        name: '전세 안전진단 이용 방법 (3단계)',
        step: howToSteps.map((s, i) => ({
          '@type': 'HowToStep',
          position: i + 1,
          name: s.name,
          text: s.text,
        })),
      },
    ],
  }
}

export default function Landing() {
  useJsonLd('landing-jsonld', jsonLdFor(FAQ_ITEMS, HOW_TO_STEPS))

  return (
    <div className="w-full">
      {/* Hero */}
      <div className="border-b border-gray-200 bg-white px-5 py-14 text-center sm:py-20">
        <h1 className="mx-auto max-w-2xl text-2xl leading-snug font-extrabold text-gray-900 sm:text-3xl">
          주소와 보증금만 넣으면
          <br />
          5초 만에 리포트를 뽑는 전세 안전 진단 계산기
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-relaxed text-gray-600">
          국토교통부 실거래가·대법원 등기부·건축물대장 공공데이터를 종합해 위험도를 계산합니다.
          "괜찮을 것 같다" 대신 숫자와 근거로 판단하세요.
        </p>
        <Link
          to="/step1"
          className="mt-8 inline-flex h-14 items-center justify-center rounded-xl bg-gray-900 px-8 text-[15px] font-bold text-white"
        >
          무료로 안전진단 시작하기
        </Link>
      </div>

      {/* Section A: 5대 전세사기 유형 */}
      <section className="mx-auto max-w-2xl px-5 py-12">
        <h2 className="text-lg font-bold text-gray-900">5대 전세사기 유형과 본 서비스의 검증 범위</h2>
        <div className="mt-6 flex flex-col gap-5">
          {FRAUD_TYPES.map((item) => (
            <div key={item.title} className="rounded-xl border border-gray-200 bg-white p-4">
              <div className="text-[14px] font-bold text-gray-900">{item.title}</div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-gray-600">{item.body}</p>
              <p className="mt-2 text-[12px] leading-relaxed text-gray-500">
                <span className="font-semibold text-gray-700">검증 방법: </span>
                {item.coverage}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Section B: FAQ */}
      <section className="border-t border-gray-200 bg-white px-5 py-12">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-lg font-bold text-gray-900">계약 전 반드시 확인해야 할 등기부등본 체크리스트</h2>
          <div className="mt-6 flex flex-col gap-5">
            {FAQ_ITEMS.map((item) => (
              <div key={item.q}>
                <div className="text-[14px] font-bold text-gray-900">Q. {item.q}</div>
                <p className="mt-1.5 text-[13px] leading-relaxed text-gray-600">A. {item.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section C: 사용법 가이드 */}
      <section className="mx-auto max-w-2xl px-5 py-12">
        <h2 className="text-lg font-bold text-gray-900">사용법 가이드 (3단계)</h2>
        <div className="mt-6 flex flex-col gap-4">
          {HOW_TO_STEPS.map((step, i) => (
            <div key={step.name} className="flex gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-900 text-[13px] font-bold text-white">
                {i + 1}
              </div>
              <div>
                <div className="text-[14px] font-bold text-gray-900">{step.name}</div>
                <p className="mt-0.5 text-[13px] leading-relaxed text-gray-600">{step.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 이런 분들께 추천 */}
      <section className="border-t border-gray-200 bg-white px-5 py-12">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-lg font-bold text-gray-900">이럴 때 확인해보세요</h2>
          <ul className="mt-5 flex flex-col gap-2.5">
            {USE_CASES.map((text) => (
              <li key={text} className="flex gap-2 text-[13px] leading-relaxed text-gray-600">
                <span className="shrink-0 text-gray-400">•</span>
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* 하단 CTA */}
      <div className="px-5 py-14 text-center">
        <Link
          to="/step1"
          className="inline-flex h-14 items-center justify-center rounded-xl bg-gray-900 px-8 text-[15px] font-bold text-white"
        >
          무료로 안전진단 시작하기
        </Link>
        <p className="mt-4 text-xs text-gray-400">회원가입 없이 무료로 이용할 수 있습니다.</p>
        <div className="mt-6 flex items-center justify-center gap-4 text-[12px] text-gray-500">
          <Link to="/terms" className="underline underline-offset-2">이용약관</Link>
          <Link to="/privacy" className="underline underline-offset-2">개인정보처리방침</Link>
        </div>
      </div>
    </div>
  )
}
