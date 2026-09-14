// 원 단위 정수를 "6억 5,050만원" 같은 한국어 표기로 변환한다.
export function formatKRW(won) {
  if (won == null) return '-'
  const eok = Math.floor(won / 100_000_000)
  const man = Math.floor((won % 100_000_000) / 10_000)
  const parts = []
  if (eok > 0) parts.push(`${eok}억`)
  if (man > 0) parts.push(`${man.toLocaleString()}만`)
  if (parts.length === 0) parts.push(won.toLocaleString())
  return parts.join(' ') + '원'
}

// property_aggregator.py / market_price_estimator.py 계약: marketPrice는 "만원" 단위.
export function formatManwonAsKRW(manwon) {
  if (manwon == null) return '-'
  return formatKRW(manwon * 10_000)
}
