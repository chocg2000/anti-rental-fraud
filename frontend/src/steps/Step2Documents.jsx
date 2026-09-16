import { useRef } from 'react'
import ScreenShell from '../components/ScreenShell'
import Toast from '../components/Toast'
import { IconAlertTriangle, IconInfoCircle, IconUploadCloud, IconSpinner, IconCheckCircle } from '../components/icons'
import { uploadRegistryPdf } from '../lib/api'

const VIOLATION_OPTIONS = [
  { id: 'clean', label: '위반건축물 아님' },
  { id: 'violation', label: '위반건축물 확인됨' },
]

const TAX_OPTIONS = [
  { id: 'yes', label: '제출함' },
  { id: 'no', label: '제출 안 함' },
]

const FIXED_DATE_OPTIONS = [
  { id: 'yes', label: '받았음' },
  { id: 'no', label: '아직 안 받음' },
]

// <input type="date">가 min/max 없이 손으로 빠르게 타이핑하면 연도 칸에 자릿수가
// 밀려 들어가는(예: "202609") 브라우저 버그가 있다 — 범위를 지정하면 방지된다.
// 완납증명서 발급일은 이미 발급된 문서이므로 미래일 수 없다.
const today = new Date().toISOString().slice(0, 10)
const MIN_TAX_ISSUE_DATE = `${new Date().getFullYear() - 5}-01-01`

export default function Step2Documents({ documents, onChange, onSubmit, submitting, submitError, onDismissSubmitError }) {
  const fileInputRef = useRef(null)
  const toastMessage = documents.uploadError || submitError

  const dismissToast = () => {
    if (documents.uploadError) onChange((prev) => ({ ...prev, uploadError: null }))
    else onDismissSubmitError()
  }

  async function handleFileSelected(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    onChange((prev) => ({ ...prev, uploadState: 'uploading', uploadError: null }))
    try {
      const result = await uploadRegistryPdf(file)
      onChange((prev) => ({
        ...prev,
        uploadState: 'uploaded',
        uploadError: null,
        registryOcrText: result.registryOcrText,
        registryPreview: {
          owners: result.owners,
          activeRights: result.activeRights,
          totalSeniorSecuredAmount: result.totalSeniorSecuredAmount,
          sourcePage: result.sourcePage,
          ownershipHistory: result.ownershipHistory,
        },
      }))
    } catch (err) {
      onChange((prev) => ({ ...prev, uploadState: 'idle', uploadError: err.message }))
    }
  }

  function resetUpload() {
    onChange((prev) => ({ ...prev, uploadState: 'idle', registryOcrText: '', registryPreview: null }))
  }

  const footerBlocked = documents.violationChoice === null

  return (
    <ScreenShell
      step={2}
      subtitle="STEP 2 / 3"
      title="서류 확인 및 자가진단"
      toast={<Toast message={toastMessage} onDismiss={dismissToast} />}
      footer={
        <div className="flex flex-col gap-2">
          {footerBlocked && <div className="text-center text-[11.5px] text-red-600">위반건축물 자가진단을 완료해주세요</div>}
          <button
            type="button"
            disabled={footerBlocked || submitting}
            onClick={onSubmit}
            className={`flex h-14 w-full items-center justify-center gap-2 rounded-xl text-[15px] font-bold ${
              footerBlocked || submitting ? 'bg-gray-200 text-gray-400' : 'bg-gray-900 text-white'
            }`}
          >
            {submitting && <IconSpinner size={18} />}
            {submitting ? '진단 중...' : '진단 시작하기'}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-7">
        {/* Section A: violation self-check */}
        <div className="flex flex-col gap-2.5">
          <div className="text-sm font-bold text-gray-900">
            위반건축물 자가진단 <span className="text-red-600">*필수</span>
          </div>

          <div className="flex gap-2.5 rounded-xl border border-orange-200 bg-orange-50 p-3">
            <IconAlertTriangle size={18} className="mt-0.5 shrink-0 text-orange-600" />
            <div className="text-[12.5px] leading-relaxed text-orange-900">
              정부 API 제한으로 건축물대장의 '위반건축물' 표시 여부를 자동으로 확인할 수 없습니다. 건축물대장 PDF 또는 세움터에서 직접 확인 후 아래에서 선택해주세요.
            </div>
          </div>

          <div className="flex gap-2">
            {VIOLATION_OPTIONS.map((opt) => {
              const selected = documents.violationChoice === opt.id
              const activeClass =
                opt.id === 'violation'
                  ? 'border-red-600 bg-red-600 text-white'
                  : 'border-gray-900 bg-gray-900 text-white'
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, violationChoice: opt.id }))}
                  className={`h-11 flex-1 rounded-lg border text-[13px] font-semibold ${
                    selected ? activeClass : 'border-gray-300 bg-white text-gray-700'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

          {documents.violationChoice === 'violation' && (
            <div className="text-xs leading-relaxed text-red-600">위반건축물이 확인되면 최종 진단 등급이 '위험'으로 표시됩니다.</div>
          )}
        </div>

        {/* Section B: registry PDF upload */}
        <div className="flex flex-col gap-2.5">
          <div className="text-sm font-bold text-gray-900">
            등기부등본 업로드 <span className="font-normal text-gray-400">(선택)</span>
          </div>

          <input ref={fileInputRef} type="file" accept="application/pdf" className="hidden" onChange={handleFileSelected} />

          {documents.uploadState === 'idle' && (
            <div className="flex flex-col items-center gap-2.5 rounded-xl border-[1.5px] border-dashed border-gray-400 bg-gray-50 px-4 py-7">
              <IconUploadCloud className="text-gray-500" />
              <div className="text-center text-[13px] text-gray-700">등기부등본 '주요 등기사항 요약' 페이지가 포함된 PDF를 업로드하세요</div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="h-10 rounded-lg border border-gray-900 bg-gray-900 px-5 text-[13px] font-semibold text-white"
              >
                PDF 선택
              </button>
            </div>
          )}

          {documents.uploadState === 'uploading' && (
            <div className="flex flex-col items-center gap-2.5 rounded-xl border border-gray-200 bg-gray-50 px-4 py-8">
              <IconSpinner />
              <div className="text-[13px] text-gray-700">PDF를 분석하고 있습니다…</div>
              <div className="text-[11px] text-gray-400">요약 페이지를 찾아 OCR을 돌리는 중 — 보통 몇 초 걸려요</div>
            </div>
          )}

          {documents.uploadState === 'uploaded' && documents.registryPreview && (
            <div className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50 p-3.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[12.5px] font-semibold text-green-600">
                  <IconCheckCircle size={14} />
                  {documents.registryPreview.sourcePage}페이지에서 요약 페이지를 찾았습니다
                </div>
                <button type="button" onClick={resetUpload} className="text-xs text-gray-500 underline">
                  다시 업로드
                </button>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-700">
                  OCR 인식 결과 <span className="font-normal text-gray-400">— 오탈자가 있으면 직접 수정하세요</span>
                </label>
                <textarea
                  rows={6}
                  value={documents.registryOcrText}
                  onChange={(e) => {
                    const value = e.target.value
                    onChange((prev) => ({ ...prev, registryOcrText: value }))
                  }}
                  className="w-full resize-y rounded-lg border border-gray-300 p-2.5 font-mono text-[12.5px] leading-relaxed text-gray-900 focus:border-gray-900 focus:outline-none"
                />
                <div className="text-[11px] text-gray-400">* 이 텍스트가 최종 진단 요청에 그대로 전달됩니다</div>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-gray-700">최초 인식 결과 (참고용)</label>
                <div className="flex flex-wrap gap-1.5">
                  {documents.registryPreview.owners.map((o, i) => (
                    <span key={i} className="rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] text-indigo-700">
                      {o.ownerName} · {o.shareType}
                    </span>
                  ))}
                  {documents.registryPreview.owners.length === 0 && (
                    <span className="text-[11px] text-gray-400">소유자 정보를 찾지 못했습니다</span>
                  )}
                </div>
                {documents.registryPreview.activeRights.map((r, i) => (
                  <div key={i} className="flex justify-between rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-[12.5px]">
                    <span className="text-gray-700">
                      [{r.rank}순위] {r.rightType}
                    </span>
                    <span className="font-semibold text-gray-900">{r.amount != null ? r.amount.toLocaleString() + '원' : '-'}</span>
                  </div>
                ))}
              </div>

              {documents.registryPreview.ownershipHistory?.length > 0 && (
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-semibold text-gray-700">
                    갑구 소유권 이전 이력 <span className="font-normal text-gray-400">(자동 인식, 오래된 순)</span>
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {documents.registryPreview.ownershipHistory.map((h, i) => (
                      <span key={i} className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] text-amber-700">
                        {h.date || '날짜 미상'} · {h.ownerName}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between border-t border-dashed border-gray-300 pt-2">
                <span className="text-[12.5px] font-semibold text-gray-700">선순위채권 합계</span>
                <span className="text-[15px] font-bold text-gray-900">
                  {documents.registryPreview.totalSeniorSecuredAmount.toLocaleString()}원
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Section C: tax clearance */}
        <div className="flex flex-col gap-2.5">
          <div className="text-sm font-bold text-gray-900">
            국세·지방세 완납증명서 <span className="font-normal text-gray-400">(선택)</span>
          </div>

          <div className="flex gap-2">
            {TAX_OPTIONS.map((opt) => {
              const selected = documents.taxChoice === opt.id
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, taxChoice: opt.id }))}
                  className={`h-11 flex-1 rounded-lg border text-[13px] font-semibold ${
                    selected ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 bg-white text-gray-700'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

          {documents.taxChoice === 'yes' && (
            <div className="flex flex-col gap-2.5 pt-1">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-700">증명서상 명의자 이름</label>
                <input
                  type="text"
                  placeholder="예: 조춘근"
                  value={documents.taxDocLandlordName}
                  onChange={(e) => {
                    const value = e.target.value
                    onChange((prev) => ({ ...prev, taxDocLandlordName: value }))
                  }}
                  className="h-11 rounded-lg border border-gray-300 px-2.5 text-[13px] focus:border-gray-900 focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-700">발급일</label>
                <input
                  type="date"
                  value={documents.taxIssueDate}
                  onChange={(e) => {
                    const value = e.target.value
                    onChange((prev) => ({ ...prev, taxIssueDate: value }))
                  }}
                  min={MIN_TAX_ISSUE_DATE}
                  max={today}
                  className="h-11 rounded-lg border border-gray-300 px-2.5 text-[13px] text-gray-900 focus:border-gray-900 focus:outline-none"
                />
              </div>
            </div>
          )}

          {documents.taxChoice === 'no' && (
            <div className="text-xs leading-relaxed text-gray-400">
              미제출은 참고용 위험 신호로 진단 결과에 반영됩니다 (통상 계약 당일 발급받는 서류입니다).
            </div>
          )}
        </div>

        {/* Section D: fixed-date (확정일자) status */}
        <div className="flex flex-col gap-2.5">
          <div className="text-sm font-bold text-gray-900">
            확정일자 <span className="font-normal text-gray-400">(선택)</span>
          </div>

          <div className="flex gap-2">
            {FIXED_DATE_OPTIONS.map((opt) => {
              const selected = documents.fixedDateChoice === opt.id
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, fixedDateChoice: opt.id }))}
                  className={`h-11 flex-1 rounded-lg border text-[13px] font-semibold ${
                    selected ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 bg-white text-gray-700'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

          {documents.fixedDateChoice === 'no' && (
            <div className="flex gap-2 rounded-lg bg-gray-50 p-2.5 text-xs leading-relaxed text-gray-500">
              <IconInfoCircle size={14} className="mt-0.5 shrink-0 text-gray-400" />
              <span>
                아직 계약 전이신가요? 확정일자는 계약서 작성 후에만 받을 수 있으므로 지금
                단계에서는 없는 게 정상입니다. 다만 이미 잔금까지 치르셨다면 이야기가 다릅니다
                — 확정일자 없이는 우선변제권이 생기지 않으니, 계약 당일 바로 주민센터나
                인터넷등기소에서 받으세요.
              </span>
            </div>
          )}
        </div>
      </div>
    </ScreenShell>
  )
}
