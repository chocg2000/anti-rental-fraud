import { useState } from 'react'
import ScreenShell from '../components/ScreenShell'
import { GradeIcon, IconChevronDown } from '../components/icons'
import { GRADE_META, RISK_BADGE, RISK_LABEL } from '../lib/grade'
import { formatManwonAsKRW } from '../lib/format'

const CONFIDENCE_META = {
  high: { label: '신뢰도 높음', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  low: { label: '신뢰도 낮음', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  estimated_from_public_price: { label: '공시가격 추정', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  unavailable: { label: '확인 불가', className: 'bg-gray-100 text-gray-500 border-gray-200' },
}

function Card({ title, badgeLabel, badgeClass, summary, detail, expanded, onToggle, extra }) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200">
      <button type="button" onClick={onToggle} className="flex w-full items-start justify-between gap-2.5 bg-white p-3.5 text-left">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-bold text-gray-900">{title}</span>
            {badgeLabel && <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${badgeClass}`}>{badgeLabel}</span>}
          </div>
          <div className="text-xs text-gray-500">{summary}</div>
          {extra}
        </div>
        <IconChevronDown size={16} className={`mt-0.5 shrink-0 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && <div className="border-t border-gray-100 px-3.5 pt-2.5 pb-3.5 text-[12.5px] leading-relaxed text-gray-700">{detail}</div>}
    </div>
  )
}

export default function Step3Result({ result, onRestart }) {
  const [expanded, setExpanded] = useState({})
  const toggle = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  const meta = GRADE_META[result.overallGrade] ?? GRADE_META.error
  const isError = result.overallGrade === 'error'
  const property = result.propertyInfo
  const deposit = result.tenancySafety?.depositPriorityRisk
  const identity = result.tenancySafety?.landlordIdentityCheck
  const fraud = result.fraudPatternResult
  const tax = result.taxClearanceResult

  const confidence = property ? CONFIDENCE_META[property.marketPriceConfidence] ?? CONFIDENCE_META.unavailable : null
  const flags = []
  if (property?.nonResidentialUseRisk) flags.push('근생빌라 의심')
  if (property?.violationStatusConfirmed && property?.violationStatusRaw) flags.push('위반건축물')

  return (
    <ScreenShell
      subtitle="진단 완료"
      title="최종 진단 결과"
      footer={
        <button type="button" onClick={onRestart} className="h-14 w-full rounded-xl border border-gray-900 bg-white text-[15px] font-bold text-gray-900">
          처음부터 다시 진단하기
        </button>
      }
    >
      <div className="flex flex-col gap-5">
        <div
          className="flex flex-col items-center gap-2.5 rounded-2xl border px-5 py-6 text-center"
          style={{ backgroundColor: meta.bg, borderColor: meta.border }}
        >
          <GradeIcon grade={result.overallGrade} style={{ color: meta.color }} />
          <div className="text-[22px] font-extrabold" style={{ color: meta.color }}>
            {meta.label}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="text-[13px] font-bold text-gray-900">판단 근거</div>
          {result.reasons.map((r, i) => (
            <div key={i} className="flex gap-2 text-[12.5px] leading-relaxed text-gray-700">
              <span className="shrink-0 text-gray-400">•</span>
              <span>{r}</span>
            </div>
          ))}
        </div>

        {isError && (
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-3.5 text-[12.5px] leading-relaxed text-gray-500">
            주소를 확인할 수 없어 시세·건축물대장·등기부 조회를 진행하지 못했습니다. 주소를 다시 확인한 뒤 처음부터 다시 시도해주세요.
          </div>
        )}

        {!isError && (
          <div className="flex flex-col gap-2.5">
            <div className="text-[13px] font-bold text-gray-900">세부 항목</div>

            {property && (
              <Card
                title="매물 정보 (시세·건축물대장)"
                badgeLabel={confidence?.label}
                badgeClass={confidence?.className}
                summary={`추정 시세 ${formatManwonAsKRW(property.marketPrice)}`}
                detail={property.marketPriceBasis}
                expanded={!!expanded.property}
                onToggle={() => toggle('property')}
                extra={
                  flags.length > 0 && (
                    <div className="mt-0.5 flex flex-wrap gap-1.5">
                      {flags.map((f) => (
                        <span key={f} className="rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-[10.5px] text-orange-600">
                          {f}
                        </span>
                      ))}
                    </div>
                  )
                }
              />
            )}

            {deposit && (
              <Card
                title="깡통전세 위험 (LTV)"
                badgeLabel={deposit.riskyDepositPriority === null ? '확인 불가' : deposit.riskyDepositPriority ? '위험' : '안전'}
                badgeClass={deposit.riskyDepositPriority === null ? RISK_BADGE.unknown : deposit.riskyDepositPriority ? RISK_BADGE.danger : RISK_BADGE.safe}
                summary={deposit.riskyDepositPriority ? '선순위채권 + 보증금이 시세의 안전 임계값 초과' : '선순위채권 + 보증금이 안전 임계값 이내'}
                detail={deposit.reason}
                expanded={!!expanded.deposit}
                onToggle={() => toggle('deposit')}
              />
            )}

            {identity && (
              <Card
                title="임대인 일치 확인"
                badgeLabel={RISK_LABEL[identity.riskLevel]}
                badgeClass={RISK_BADGE[identity.riskLevel]}
                summary={identity.match === false ? '계약서 임대인과 등기부 소유자가 다릅니다' : identity.reason}
                detail={identity.reason}
                expanded={!!expanded.identity}
                onToggle={() => toggle('identity')}
              />
            )}

            <Card
              title="사기 패턴 탐지"
              badgeLabel={fraud ? (fraud.triggered ? '패턴 의심' : '해당 없음') : '판별 불가'}
              badgeClass={fraud ? (fraud.triggered ? RISK_BADGE.warning : RISK_BADGE.safe) : RISK_BADGE.unknown}
              summary={fraud ? fraud.reason : '건축물대장 정보를 확인하지 못해 판별할 수 없습니다.'}
              detail={fraud ? fraud.reason : '건축물대장 조회가 실패했거나 사용승인일 정보가 없어 신축빌라 패턴을 판별하지 못했습니다.'}
              expanded={!!expanded.fraud}
              onToggle={() => toggle('fraud')}
            />

            <Card
              title="완납증명서 확인"
              badgeLabel={tax ? RISK_LABEL[tax.riskLevel] : '정보 없음'}
              badgeClass={tax ? RISK_BADGE[tax.riskLevel] : RISK_BADGE.unknown}
              summary={tax ? tax.reason : '완납증명서 정보를 입력하지 않았습니다.'}
              detail={tax ? tax.reason : '이 항목은 선택 입력이라 값이 없으면 진단에 반영되지 않습니다.'}
              expanded={!!expanded.tax}
              onToggle={() => toggle('tax')}
            />
          </div>
        )}
      </div>
    </ScreenShell>
  )
}
