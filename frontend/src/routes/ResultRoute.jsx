import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import ScreenShell from '../components/ScreenShell'
import { IconSpinner } from '../components/icons'
import Step3Result from '../steps/Step3Result'
import { getAssessment } from '../lib/api'

// /result/:id — POST /assessment 직후엔 location.state로 넘겨받은 결과를 바로 쓰고(빠른 경로),
// 새로고침되거나 링크를 통해 곧장 열린 경우엔 GET /assessment/:id로 다시 불러온다.
export default function ResultRoute({ onRestart }) {
  const { id } = useParams()
  const location = useLocation()
  const passedResult = location.state?.result

  const [result, setResult] = useState(passedResult && passedResult.id === id ? passedResult : null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(!(passedResult && passedResult.id === id))

  useEffect(() => {
    if (passedResult && passedResult.id === id) return

    let cancelled = false
    setLoading(true)
    setError(null)

    getAssessment(id)
      .then((data) => {
        if (!cancelled) setResult(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (loading) {
    return (
      <ScreenShell subtitle="진단 완료" title="최종 진단 결과">
        <div className="flex flex-col items-center gap-3 py-16">
          <IconSpinner />
          <div className="text-sm text-gray-500">결과를 불러오는 중...</div>
        </div>
      </ScreenShell>
    )
  }

  if (error || !result) {
    return (
      <ScreenShell subtitle="오류" title="결과를 찾을 수 없습니다">
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="text-sm text-gray-500">
            {error || '이 링크는 만료되었거나 잘못됐을 수 있습니다.'}
          </div>
          <button
            type="button"
            onClick={onRestart}
            className="h-12 rounded-xl bg-gray-900 px-6 text-sm font-bold text-white"
          >
            처음부터 다시 진단하기
          </button>
        </div>
      </ScreenShell>
    )
  }

  return <Step3Result result={result} onRestart={onRestart} />
}
