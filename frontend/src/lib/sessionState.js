// 새로고침해도 Step1/Step2 입력이 안 날아가게 sessionStorage에 살짝 저장해두는 용도.
// 사파리 프라이빗 모드 등에서 sessionStorage 접근 자체가 막힐 수 있어 항상 try/catch로 감싼다.
const PREFIX = 'jeonse-safety:'

export function loadSessionState(key, fallback) {
  try {
    const raw = sessionStorage.getItem(PREFIX + key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

export function saveSessionState(key, value) {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    // 저장 실패는 무시 — 이 기능이 없어도 앱 자체는 동작해야 한다.
  }
}

export function clearSessionState(key) {
  try {
    sessionStorage.removeItem(PREFIX + key)
  } catch {
    // ignore
  }
}
