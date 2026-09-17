import { Link } from 'react-router-dom'
import { useNoIndex } from '../lib/seo'
import { SHORT_TERMS, SHORT_PRIVACY, TERMS_TEXT, PRIVACY_POLICY_TEXT, SERVICE_NAME } from '../lib/policyContent'

export default function PolicyPage({ type }) {
  useNoIndex()
  const isTerms = type === 'terms'
  const title = isTerms ? '이용약관' : '개인정보처리방침'
  const sections = isTerms ? TERMS_TEXT : PRIVACY_POLICY_TEXT
  const shortList = isTerms ? SHORT_TERMS : SHORT_PRIVACY

  return (
    <div className="w-full bg-gray-50">
      <div className="mx-auto max-w-3xl px-5 py-10 sm:py-14">
        <div className="mb-6 flex items-center justify-between gap-3">
          <Link to="/step1" className="text-sm font-medium text-gray-600 underline underline-offset-2">
            ← 진단으로 돌아가기
          </Link>
          <span className="rounded-full bg-gray-900 px-3 py-1 text-[11px] font-semibold text-white">
            {SERVICE_NAME}
          </span>
        </div>

        <article className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="mt-4 text-sm leading-relaxed text-gray-600">
            본 문서는 서비스 이용 전 필수 확인 사항을 상시 공개하기 위한 정책 페이지입니다. 자세한 내용은 아래 본문을 확인해 주세요.
          </p>

          <div className="mt-8 rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="mb-2 text-sm font-bold text-amber-900">핵심 요약</div>
            <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-amber-900">
              {shortList.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>

          <div className="mt-8 space-y-6">
            {sections.map((section) => (
              <section key={section.title} className="border-b border-gray-200 pb-4 last:border-b-0 last:pb-0">
                <h2 className="text-base font-bold text-gray-900">{section.title}</h2>
                <p className="mt-2 text-sm leading-7 text-gray-700">{section.body}</p>
              </section>
            ))}
          </div>
        </article>
      </div>
    </div>
  )
}
