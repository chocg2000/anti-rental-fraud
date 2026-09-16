import { useState } from 'react'
import ScreenShell from '../components/ScreenShell'
import { GradeIcon, IconChevronDown, IconAlertTriangle } from '../components/icons'
import PossessionTimeline from '../components/PossessionTimeline'
import OwnershipTimeline from '../components/OwnershipTimeline'
import { GRADE_META, RISK_BADGE, RISK_LABEL } from '../lib/grade'
import { formatManwonAsKRW, formatKRW } from '../lib/format'

const CONFIDENCE_META = {
  high: { label: '신뢰도 높음', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  low: { label: '신뢰도 낮음', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  estimated_from_public_price: { label: '공시가격 추정', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  unavailable: { label: '확인 불가', className: 'bg-gray-100 text-gray-500 border-gray-200' },
}

function Card({ title, badgeLabel, badgeClass, summary, detail, expanded, onToggle, extra }) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200">
      <button type="button" onClick={onToggle} className="flex w-full items-center justify-between gap-2.5 bg-white p-3.5 text-left">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-bold text-gray-900">{title}</span>
            {badgeLabel && <span className={`rounded-full border px-2 py-0.5 text-[10.5px] ${badgeClass}`}>{badgeLabel}</span>}
          </div>
          <div className="text-[12.5px] font-semibold text-gray-700">{summary}</div>
          {extra}
        </div>
        <IconChevronDown size={16} className={`shrink-0 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && <div className="border-t border-gray-100 px-3.5 pt-2.5 pb-3.5 text-[12.5px] leading-relaxed text-gray-700">{detail}</div>}
    </div>
  )
}

// "라벨 — 설명" 패턴으로 된 reason 문자열을 두 줄로 나눠서 렌더링하기 위한 분리.
// (백엔드 도메인 룰들이 전부 이 포맷으로 reason을 만들어서 씀 — tenancy_safety_rules.py 등)
function splitReason(text) {
  const idx = text.indexOf(' — ')
  if (idx === -1) return { label: null, detail: text }
  return { label: text.slice(0, idx), detail: text.slice(idx + 3) }
}

const FRAUD_ACTION_STEPS = [
  {
    title: '계약 잠정 보류 및 이전 계약서 요구',
    body: '중개사에게 "직전 소유권 이전 당시의 매매계약서" 또는 "실제 거래 금액 확인원"을 보여달라고 요구하세요. 신축 분양가보다 전세 보증금이 더 높거나 같다면(깡통전세 위험), 계약을 즉시 중단해야 합니다.',
  },
  {
    title: '국세·지방세 완납증명서 즉시 확인',
    body: '바지사장 명의 변경 패턴은 임대인의 세금 체납으로 건물이 압류될 확률이 높습니다. 계약서 특약에 "잔금일 익일까지 임대인의 세금 체납이 발견되거나 소유권이 변경되면 계약은 무효로 하고 배액배상한다"는 문구를 넣으세요.',
  },
  {
    title: '주변 매매 시세 직접 발품 팔기',
    body: '신축 빌라는 감정평가액이 부풀려지기 쉽습니다. 앱의 추정 시세 외에 인근 공인중개사 3곳 이상을 직접 방문해 "이 동네 신축 빌라 진짜 매매 시세"를 교차 검증하세요.',
  },
]

function FraudActionPlan() {
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-gray-200 bg-white p-3.5">
      <div className="text-xs font-bold text-gray-900">💡 위험을 피하기 위한 3단계 즉시 행동 가이드</div>
      {FRAUD_ACTION_STEPS.map((s, i) => (
        <div key={i} className="flex gap-2.5">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-600 text-[11px] font-bold text-white">
            {i + 1}
          </div>
          <div className="flex flex-col gap-0.5">
            <div className="text-[12.5px] font-bold text-gray-900">{s.title}</div>
            <div className="text-[11.5px] leading-relaxed text-gray-600">{s.body}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Step3Result({ result, onRestart }) {
  const [expanded, setExpanded] = useState(() => ({ fraud: !!result.fraudPatternResult?.triggered }))
  const toggle = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  const meta = GRADE_META[result.overallGrade] ?? GRADE_META.error
  const isError = result.overallGrade === 'error'
  const property = result.propertyInfo
  const deposit = result.tenancySafety?.depositPriorityRisk
  const identity = result.tenancySafety?.landlordIdentityCheck
  const gapRisk = result.tenancySafety?.possessionPriorityGapRisk
  const fixedDate = result.tenancySafety?.fixedDateRisk
  const priorityRepayment = result.tenancySafety?.minimumPriorityRepayment
  const fraud = result.fraudPatternResult
  const tax = result.taxClearanceResult

  // 사기 패턴 단독으로는 항상 warning이지만(overall_safety_assessment.py), 다른 위험
  // 신호와 겹쳐 최종 등급이 danger까지 올라간 경우엔 헤드라인도 그에 맞춰 escalate한다.
  const fraudSeverity = result.overallGrade === 'danger' ? 'danger' : 'warning'

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

        {fraud?.triggered && (
          <div
            className={`flex items-start gap-2.5 rounded-2xl border p-4 ${
              fraudSeverity === 'danger' ? 'border-red-200 bg-red-50' : 'border-orange-200 bg-orange-50'
            }`}
          >
            <IconAlertTriangle size={20} className={`mt-0.5 shrink-0 ${fraudSeverity === 'danger' ? 'text-red-600' : 'text-orange-600'}`} />
            <div className="flex flex-col gap-1">
              <div className={`text-[15px] font-extrabold ${fraudSeverity === 'danger' ? 'text-red-700' : 'text-orange-700'}`}>
                ⚠️ 전형적인 전세사기 의심 패턴 감지
              </div>
              <div className="text-[12.5px] leading-relaxed text-gray-700">
                신축 빌라(사용승인 1년 이내) + 최근 소유권 변경 이력이 함께 확인되었습니다. 아래 "사기 패턴 탐지" 항목의 타임라인과 행동 가이드를 꼭 확인하세요.
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <div className="text-[13px] font-bold text-gray-900">판단 근거</div>
          {result.reasons.map((r, i) => {
            const { label, detail } = splitReason(r)
            return (
              <div key={i} className="flex gap-2 text-[12.5px] text-gray-700">
                <span className="shrink-0 text-gray-400">•</span>
                <span className="min-w-0 flex-1">
                  {label && <span className="block font-semibold text-gray-900">{label}</span>}
                  <span className="block leading-[1.7]">{detail}</span>
                </span>
              </div>
            )
          })}
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

            {gapRisk && (
              <Card
                title="대항력 공백 위험"
                badgeLabel={gapRisk.gapRiskDetected === null ? '확인 불가' : gapRisk.gapRiskDetected ? '위험' : '안전'}
                badgeClass={gapRisk.gapRiskDetected === null ? RISK_BADGE.unknown : gapRisk.gapRiskDetected ? RISK_BADGE.danger : RISK_BADGE.safe}
                summary={gapRisk.gapRiskDetected ? '잔금(입주)일 당일 접수된 권리가 있습니다' : gapRisk.reason}
                detail={
                  <div className="flex flex-col gap-3">
                    <div>{gapRisk.reason}</div>
                    {gapRisk.moveInDate && (
                      <PossessionTimeline moveInDate={gapRisk.moveInDate} rightsTimeline={gapRisk.rightsTimeline} />
                    )}
                  </div>
                }
                expanded={!!expanded.gapRisk}
                onToggle={() => toggle('gapRisk')}
              />
            )}

            {fixedDate && (
              <Card
                title="확정일자 확보 여부"
                badgeLabel={RISK_LABEL[fixedDate.riskLevel]}
                badgeClass={RISK_BADGE[fixedDate.riskLevel]}
                summary={fixedDate.reason}
                detail={fixedDate.reason}
                expanded={!!expanded.fixedDate}
                onToggle={() => toggle('fixedDate')}
              />
            )}

            {priorityRepayment && (
              <Card
                title="최우선변제금 (소액임차인 보호)"
                badgeLabel={
                  priorityRepayment.status === 'ok' ? '보호됨'
                  : priorityRepayment.status === 'not_eligible' ? '해당 없음'
                  : '확인 불가'
                }
                badgeClass={
                  priorityRepayment.status === 'ok' ? RISK_BADGE.safe
                  : priorityRepayment.status === 'not_eligible' ? RISK_BADGE.unknown
                  : RISK_BADGE.unknown
                }
                summary={
                  priorityRepayment.status === 'ok'
                    ? `경매로 넘어가도 최우선 ${formatKRW(priorityRepayment.guaranteedAmount)} 보장`
                    : priorityRepayment.reason
                }
                detail={priorityRepayment.reason}
                expanded={!!expanded.priorityRepayment}
                onToggle={() => toggle('priorityRepayment')}
              />
            )}

            <Card
              title="사기 패턴 탐지"
              badgeLabel={fraud ? (fraud.triggered ? '패턴 의심' : '해당 없음') : '판별 불가'}
              badgeClass={fraud ? (fraud.triggered ? RISK_BADGE.warning : RISK_BADGE.safe) : RISK_BADGE.unknown}
              summary={fraud ? fraud.reason : '건축물대장 정보를 확인하지 못해 판별할 수 없습니다.'}
              detail={
                fraud ? (
                  <div className="flex flex-col gap-3">
                    <div>{fraud.reason}</div>
                    {fraud.triggered && (
                      <>
                        <OwnershipTimeline
                          useApprovalDate={property?.building?.useApprovalDate}
                          ownershipHistory={fraud.ownershipHistory}
                          suspiciousDate={fraud.latestTransferDate}
                          contractDate={gapRisk?.moveInDate}
                        />
                        <FraudActionPlan />
                      </>
                    )}
                  </div>
                ) : (
                  '건축물대장 조회가 실패했거나 사용승인일 정보가 없어 신축빌라 패턴을 판별하지 못했습니다.'
                )
              }
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
