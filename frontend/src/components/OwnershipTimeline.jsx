import { IconAlertTriangle } from './icons'

// 건축물대장 사용승인일("YYYYMMDD")을 다른 날짜들과 같은 "YYYY-MM-DD" 포맷으로 맞춘다.
function toIsoDate(yyyymmdd) {
  if (!yyyymmdd || !/^\d{8}$/.test(yyyymmdd)) return null
  return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6, 8)}`
}

// fraudPatternResult가 돌려주는 ownershipHistory(갑구 소유권 이전 이력, 클로바 OCR 기반)를
// 사용승인일 · 현재 계약(입주) 시점과 하나의 시간축으로 합쳐서 보여준다. PossessionTimeline과
// 같은 원칙 — 데이터가 없는 지점을 추측해서 채우지 않는다. useApprovalDate도 이력도 전혀
// 없으면 아예 렌더링하지 않는다.
// 이력의 첫 항목은 "최초 소유권 등록"으로 표기한다 — fraud.triggered가 true일 때만 이
// 컴포넌트가 쓰이고, triggered는 isNewBuilding(신축)을 전제로 하므로 건물 자체가 생긴 지
// 얼마 안 됐다는 뜻이라 첫 이력이 곧 최초 등기라는 추정이 안전하다(단정은 피해 "통상"으로 표현).
export default function OwnershipTimeline({ useApprovalDate, ownershipHistory, suspiciousDate, contractDate }) {
  const approvalIso = toIsoDate(useApprovalDate)
  const datedHistory = (ownershipHistory ?? [])
    .filter((h) => h.date)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))

  if (!approvalIso && datedHistory.length === 0) return null

  const events = []
  if (approvalIso) {
    events.push({ date: approvalIso, label: '건물 완공 (사용승인)', detail: null, suspicious: false })
  }
  datedHistory.forEach((h, i) => {
    events.push({
      date: h.date,
      label: i === 0 ? '최초 소유권 등록' : '소유권 이전',
      detail: i === 0 ? `${h.ownerName} · 통상 시행사/건축주 명의` : `${h.ownerName} · 매매가격 확인 필요`,
      suspicious: suspiciousDate != null && h.date === suspiciousDate,
    })
  })
  if (contractDate) {
    events.push({ date: contractDate, label: '현재 전세 계약(입주) 시점', detail: null, suspicious: false })
  }
  events.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50/40 p-3.5">
      <div className="text-xs font-semibold text-gray-700">소유권 변동 타임라인</div>
      <div className="flex flex-col">
        {events.map((ev, i) => {
          const isLast = i === events.length - 1
          const nextIsSuspicious = !isLast && events[i + 1].suspicious
          return (
            <div key={i} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${ev.suspicious ? 'bg-red-600' : 'bg-gray-400'}`} />
                {!isLast && (
                  <div className={nextIsSuspicious ? 'w-0 flex-1 border-l-2 border-dashed border-red-400' : 'w-px flex-1 bg-gray-300'} />
                )}
              </div>
              <div className="min-w-0 flex-1 pb-3.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12.5px] font-bold text-gray-900">{ev.date}</span>
                  <span className={`text-[12.5px] font-semibold ${ev.suspicious ? 'text-red-600' : 'text-gray-700'}`}>{ev.label}</span>
                  {ev.suspicious && <IconAlertTriangle size={13} className="text-red-600" />}
                </div>
                {ev.detail && <div className="text-[11.5px] text-gray-500">{ev.detail}</div>}
                {ev.suspicious && (
                  <div className="mt-1 inline-block rounded-full bg-red-100 px-2 py-0.5 text-[10.5px] font-semibold text-red-700">
                    ⚠️ 사기 패턴 발생 구간
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
