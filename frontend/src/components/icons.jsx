// 스트로크 기반 인라인 SVG 아이콘 (이모지/딩벳 미사용)
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }

export function IconCheckCircle({ size = 24, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.5 2.5L16 9.5" />
    </svg>
  )
}

export function IconInfoCircle({ size = 24, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="8" x2="12" y2="13" />
      <line x1="12" y1="16" x2="12" y2="16.01" />
    </svg>
  )
}

export function IconAlertTriangle({ size = 24, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <path d="M12 3L2 21h20L12 3z" />
      <line x1="12" y1="10" x2="12" y2="14" />
      <line x1="12" y1="17" x2="12" y2="17.01" />
    </svg>
  )
}

export function IconXCircle({ size = 24, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <circle cx="12" cy="12" r="9" />
      <line x1="9" y1="9" x2="15" y2="15" />
      <line x1="15" y1="9" x2="9" y2="15" />
    </svg>
  )
}

export function IconHelpCircle({ size = 24, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.35-1 .75-1 1.45" />
      <line x1="12" y1="16.5" x2="12" y2="16.5" />
    </svg>
  )
}

export function IconChevronDown({ size = 16, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

export function IconUploadCloud({ size = 28, className, style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} style={style} {...base}>
      <path d="M12 3v12" />
      <path d="M7 8l5-5 5 5" />
      <path d="M5 21h14" />
    </svg>
  )
}

export function IconClose({ size = 12, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round">
      <line x1="5" y1="5" x2="19" y2="19" />
      <line x1="19" y1="5" x2="5" y2="19" />
    </svg>
  )
}

export function IconSpinner({ size = 26, className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={`animate-spin ${className ?? ''}`}>
      <circle cx="12" cy="12" r="9" stroke="#e5e7eb" strokeWidth="3" />
      <path d="M12 3a9 9 0 0 1 9 9" stroke="#111827" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

// grade 하나를 받아 알맞은 신호등 아이콘을 고른다
export function GradeIcon({ grade, size = 40, className, style }) {
  switch (grade) {
    case 'safe':
      return <IconCheckCircle size={size} className={className} style={style} />
    case 'caution':
      return <IconInfoCircle size={size} className={className} style={style} />
    case 'warning':
      return <IconAlertTriangle size={size} className={className} style={style} />
    case 'danger':
      return <IconXCircle size={size} className={className} style={style} />
    default:
      return <IconHelpCircle size={size} className={className} style={style} />
  }
}
