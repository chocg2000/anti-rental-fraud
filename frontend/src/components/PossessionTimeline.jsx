import { IconAlertTriangle } from './icons'

// possessionPriorityGapRisk가 돌려주는 moveInDate + rightsTimeline(접수일이 확인된
// 권리만, 접수일순 정렬)을 하나의 시간축으로 합쳐서 보여준다. 데이터가 없는 지점을
// 추측해서 채우지 않는다 — moveInDate/rightsTimeline이 없으면 아예 렌더링하지 않는다.
export default function PossessionTimeline({ moveInDate, rightsTimeline }) {
  if (!moveInDate) return null

  const events = [
    { date: moveInDate, kind: 'moveIn', label: '잔금(입주)일', detail: '대항력은 다음 날 0시부터 발생' },
    ...(rightsTimeline ?? []).map((r) => ({
      date: r.receivedDate,
      kind: 'right',
      label: r.rightType ?? '권리',
      detail: `접수 당일 즉시 효력 발생${r.amount != null ? ` · ${r.amount.toLocaleString()}원` : ''}`,
    })),
  ].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.kind === 'moveIn' ? -1 : 1))

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3.5">
      <div className="text-xs font-semibold text-gray-700">대항력 발생 시점 vs 등기부 접수일</div>
      <div className="flex flex-col">
        {events.map((ev, i) => {
          const collision = ev.date === moveInDate && rightsTimeline?.some((r) => r.receivedDate === moveInDate)
          const isLast = i === events.length - 1
          return (
            <div key={i} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                    collision ? 'bg-red-600' : ev.kind === 'moveIn' ? 'bg-gray-900' : 'bg-gray-400'
                  }`}
                />
                {!isLast && <div className="w-px flex-1 bg-gray-300" />}
              </div>
              <div className="min-w-0 flex-1 pb-3.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12.5px] font-bold text-gray-900">{ev.date}</span>
                  <span className={`text-[12.5px] font-semibold ${collision ? 'text-red-600' : 'text-gray-700'}`}>
                    {ev.label}
                  </span>
                  {collision && <IconAlertTriangle size={13} className="text-red-600" />}
                </div>
                <div className="text-[11.5px] text-gray-500">{ev.detail}</div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
