import { useEffect } from 'react'

// SPA는 페이지 이동해도 <head>가 그대로 남기 때문에, 라우트마다 필요한 <meta name="robots">를
// 직접 넣고 빼야 한다. Step1/Step2/Result처럼 유저 개인 입력값·진단 결과가 담긴 페이지는
// 검색엔진에 색인되면 안 되므로(개인정보 노출 위험 + 어차피 검색 가치 없는 폼/결과 페이지)
// noindex를 걸고, 언마운트 시(다른 라우트로 이동 시) 원래 상태로 되돌린다 — 안 되돌리면
// 랜딩 페이지(/)까지 noindex가 새어나가 검색엔진에서 사이트 전체가 빠질 수 있다.
export function useNoIndex() {
  useEffect(() => {
    let tag = document.querySelector('meta[name="robots"]')
    const existed = !!tag
    const prevContent = tag?.getAttribute('content') ?? null
    if (!tag) {
      tag = document.createElement('meta')
      tag.setAttribute('name', 'robots')
      document.head.appendChild(tag)
    }
    tag.setAttribute('content', 'noindex, nofollow')

    return () => {
      if (!existed) {
        tag.remove()
      } else if (prevContent !== null) {
        tag.setAttribute('content', prevContent)
      }
    }
  }, [])
}

// FAQPage/HowTo 같은 JSON-LD는 랜딩 페이지 콘텐츠와 항상 같은 내용을 유지해야
// (schema.org 가이드라인 — 실제로 안 보이는 내용을 구조화 데이터로만 주장하면 안 됨)
// 컴포넌트 안에서 콘텐츠와 나란히 관리한다. 언마운트 시 제거해 다른 라우트로 새지 않게 한다.
export function useJsonLd(id, data) {
  useEffect(() => {
    if (!data) return
    const script = document.createElement('script')
    script.type = 'application/ld+json'
    script.id = id
    script.text = JSON.stringify(data)
    document.head.appendChild(script)
    return () => {
      script.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
}
