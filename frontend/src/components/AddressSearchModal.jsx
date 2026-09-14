import { useEffect, useRef } from 'react'
import { IconClose } from './icons'

// 다음(Daum) 우편번호 서비스 — 무료 임베드 스크립트, API 키 불필요.
// (참고: 이건 카카오 로컬 REST API(백엔드의 address_resolver.py, 주소→PNU 변환)와는
//  완전히 별개 서비스다. 이 팝업이 붙는다고 해서 백엔드 카카오 키가 검증되는 건 아니다.)
const POSTCODE_SCRIPT_SRC = '//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js'

function loadPostcodeScript() {
  return new Promise((resolve, reject) => {
    if (window.daum?.Postcode) {
      resolve()
      return
    }
    const existing = document.querySelector(`script[src="${POSTCODE_SCRIPT_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('주소 검색 스크립트를 불러오지 못했습니다.')))
      return
    }
    const script = document.createElement('script')
    script.src = POSTCODE_SCRIPT_SRC
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('주소 검색 스크립트를 불러오지 못했습니다.'))
    document.head.appendChild(script)
  })
}

export default function AddressSearchModal({ onSelect, onClose }) {
  const containerRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    loadPostcodeScript()
      .then(() => {
        if (cancelled || !containerRef.current) return
        new window.daum.Postcode({
          oncomplete: (data) => {
            const address = data.roadAddress || data.jibunAddress || data.address
            onSelect(address)
          },
          width: '100%',
          height: '100%',
        }).embed(containerRef.current)
      })
      .catch(() => {
        if (!cancelled && containerRef.current) {
          containerRef.current.textContent = '주소 검색 서비스를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.'
        }
      })

    return () => {
      cancelled = true
    }
  }, [onSelect])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <div
        className="flex h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-t-2xl bg-white sm:h-[600px] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3">
          <span className="text-sm font-bold text-gray-900">주소 검색</span>
          <button type="button" onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600">
            <IconClose size={16} />
          </button>
        </div>
        <div ref={containerRef} className="flex-1 p-4 text-center text-sm text-gray-400" />
      </div>
    </div>
  )
}
