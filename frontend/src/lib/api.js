const BASE = '/api'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function readErrorDetail(res) {
  try {
    const body = await res.json()
    return body.detail || `요청이 실패했습니다 (${res.status})`
  } catch {
    return `요청이 실패했습니다 (${res.status})`
  }
}

export async function uploadRegistryPdf(file) {
  const formData = new FormData()
  formData.append('file', file)

  let res
  try {
    res = await fetch(`${BASE}/registry/upload`, { method: 'POST', body: formData })
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.')
  }
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res))
  return res.json()
}

export async function requestAssessment(payload) {
  let res
  try {
    res = await fetch(`${BASE}/assessment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.')
  }
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res))
  return res.json()
}

// 결과 화면(/result/:id)이 새로고침되거나 링크로 공유됐을 때 다시 불러오는 용도.
// 백엔드는 프로토타입 단계라 인메모리 저장소라 서버가 재시작되면 404가 날 수 있다.
export async function getAssessment(id) {
  let res
  try {
    res = await fetch(`${BASE}/assessment/${encodeURIComponent(id)}`)
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.')
  }
  if (!res.ok) throw new ApiError(res.status, await readErrorDetail(res))
  return res.json()
}
