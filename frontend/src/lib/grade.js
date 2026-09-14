// overall_safety_assessment.py의 Grade 리터럴("safe" | "caution" | "warning" | "danger")과
// full_assessment.py가 추가하는 "error"(주소 정규화 실패) 다섯 가지를 한 곳에서 관리한다.
export const GRADE_META = {
  safe: { label: '안전', color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
  caution: { label: '주의', color: '#ca8a04', bg: '#fefce8', border: '#fde68a' },
  warning: { label: '경고', color: '#ea580c', bg: '#fff7ed', border: '#fed7aa' },
  danger: { label: '위험', color: '#dc2626', bg: '#fef2f2', border: '#fecaca' },
  error: { label: '확인 불가', color: '#6b7280', bg: '#f9fafb', border: '#e5e7eb' },
}

// tenancy_safety_rules.py / tax_clearance_check.py의 riskLevel("safe"|"caution"|"warning"|"danger"|"unknown")
export const RISK_BADGE = {
  safe: 'bg-green-50 text-green-700 border-green-200',
  caution: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  warning: 'bg-orange-50 text-orange-700 border-orange-200',
  danger: 'bg-red-50 text-red-700 border-red-200',
  unknown: 'bg-gray-100 text-gray-500 border-gray-200',
}

export const RISK_LABEL = {
  safe: '안전',
  caution: '주의',
  warning: '경고',
  danger: '위험',
  unknown: '확인 불가',
}
