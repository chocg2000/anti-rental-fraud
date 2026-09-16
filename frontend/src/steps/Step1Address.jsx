import { useState } from 'react'
import ScreenShell from '../components/ScreenShell'
import AddressSearchModal from '../components/AddressSearchModal'

// <input type="date">가 min/max 없이 손으로 빠르게 타이핑하면 연도 칸에 자릿수가
// 밀려 들어가는(예: "202609") 브라우저 버그가 있다 — 범위를 지정하면 해당 칸의
// 자릿수 한계가 강제돼 방지된다.
const today = new Date()
const MIN_DATE = `${today.getFullYear() - 1}-01-01`
const MAX_DATE = `${today.getFullYear() + 5}-12-31`

const PROPERTY_TYPES = [
  { id: 'apartment', label: '아파트' },
  { id: 'villa', label: '빌라' },
  { id: 'officetel', label: '오피스텔' },
  { id: 'multi_household', label: '다세대' },
]

export default function Step1Address({ form, onChange, onNext }) {
  const [searchOpen, setSearchOpen] = useState(false)

  const set = (key) => (e) => {
    const value = e.target.value
    onChange((prev) => ({ ...prev, [key]: value }))
  }

  const handleAddressSelected = (address) => {
    onChange((prev) => ({ ...prev, address, addressDetail: '' }))
    setSearchOpen(false)
  }

  const isValid =
    form.address.trim() !== '' &&
    Number(form.targetArea) > 0 &&
    Number(form.myDeposit) > 0 &&
    form.contractLandlordName.trim() !== '' &&
    form.privacyConsent === true

  return (
    <>
    <ScreenShell
      step={1}
      subtitle="STEP 1 / 3"
      title="매물 정보 입력"
      footer={
        <button
          type="button"
          disabled={!isValid}
          onClick={onNext}
          className={`h-14 w-full rounded-xl text-[15px] font-bold ${
            isValid ? 'bg-gray-900 text-white' : 'bg-gray-200 text-gray-400'
          }`}
        >
          다음
        </button>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-semibold text-gray-700">주소</label>
          <div className="flex gap-2">
            <input
              type="text"
              readOnly
              value={form.address}
              onClick={() => setSearchOpen(true)}
              placeholder="주소 검색을 눌러 입력하세요"
              className="h-12 flex-1 cursor-pointer rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-900"
            />
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="h-12 shrink-0 rounded-lg border border-gray-900 bg-gray-900 px-4 text-[13px] font-semibold text-white"
            >
              주소 검색
            </button>
          </div>
          {form.address && (
            <input
              type="text"
              value={form.addressDetail}
              onChange={set('addressDetail')}
              placeholder="상세주소 (동/호수, 선택)"
              className="h-12 rounded-lg border border-gray-300 px-3 text-sm text-gray-900 focus:border-gray-900 focus:outline-none"
            />
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-semibold text-gray-700">전용면적 (㎡)</label>
          <input
            type="number"
            value={form.targetArea}
            onChange={set('targetArea')}
            placeholder="예: 84.99"
            className="h-12 rounded-lg border border-gray-300 px-3 text-sm text-gray-900 focus:border-gray-900 focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-semibold text-gray-700">보증금</label>
          <div className="relative">
            <input
              type="number"
              value={form.myDeposit}
              onChange={set('myDeposit')}
              placeholder="숫자만 입력"
              className="h-12 w-full rounded-lg border border-gray-300 px-3 pr-10 text-sm text-gray-900 focus:border-gray-900 focus:outline-none"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-gray-500">원</span>
          </div>
          <div className="text-[11px] text-gray-400">예: 100000000 (1억원)</div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-semibold text-gray-700">
            임대인 이름 <span className="font-normal text-gray-400">(계약서 기준)</span>
          </label>
          <input
            type="text"
            value={form.contractLandlordName}
            onChange={set('contractLandlordName')}
            placeholder="예: 홍길동"
            className="h-12 rounded-lg border border-gray-300 px-3 text-sm text-gray-900 focus:border-gray-900 focus:outline-none"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-semibold text-gray-700">
            잔금(입주)일 <span className="font-normal text-gray-400">(선택, 전입신고 예정일)</span>
          </label>
          <input
            type="date"
            value={form.moveInDate}
            onChange={set('moveInDate')}
            min={MIN_DATE}
            max={MAX_DATE}
            className="h-12 rounded-lg border border-gray-300 px-3 text-sm text-gray-900 focus:border-gray-900 focus:outline-none"
          />
          <div className="text-[11px] text-gray-400">
            등기부상 권리 접수일과 같은 날이면 대항력 공백 위험을 진단해드려요.
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <label className="text-[13px] font-semibold text-gray-700">건물 유형</label>
          <div className="flex flex-wrap gap-2">
            {PROPERTY_TYPES.map((pt) => {
              const selected = form.propertyType === pt.id
              return (
                <button
                  key={pt.id}
                  type="button"
                  onClick={() => onChange((prev) => ({ ...prev, propertyType: pt.id }))}
                  className={`h-10 rounded-full border px-4 text-[13px] font-semibold ${
                    selected ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 bg-white text-gray-700'
                  }`}
                >
                  {pt.label}
                </button>
              )
            })}
          </div>
        </div>

        {/*
          ⚠️ 개인정보 수집·이용 동의 UI — 아래 안내 문구는 자리표시자(placeholder)입니다.
          실제 수집 항목/목적/보유기간/제3자 제공 여부는 서비스 운영 방식이 확정된 뒤
          법률 검토를 거쳐 반드시 교체해야 합니다. 이 상태로 실서비스에 배포하지 마세요.
        */}
        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-amber-300 bg-amber-50 p-3.5">
          <label className="flex items-start gap-2.5">
            <input
              type="checkbox"
              checked={form.privacyConsent === true}
              onChange={(e) => {
                const checked = e.target.checked
                onChange((prev) => ({ ...prev, privacyConsent: checked }))
              }}
              className="mt-0.5 h-4 w-4 shrink-0"
            />
            <span className="text-[13px] font-semibold text-gray-800">
              개인정보 수집·이용에 동의합니다 <span className="text-red-600">(필수)</span>
            </span>
          </label>
          <div className="text-[11px] leading-relaxed text-amber-700">
            [placeholder — 법률 검토 필요] 수집 항목: 주소, 전용면적, 보증금, 임대인 이름,
            (선택) 등기부등본 PDF. 수집 목적: 전세/월세 안전진단 결과 산출. 이 문구는
            임시 자리표시자이며, 실제 수집·이용 목적/보유기간/제3자 제공 여부를 반영한
            정식 개인정보처리방침으로 반드시 교체해야 합니다.
          </div>
        </div>
      </div>
    </ScreenShell>
    {searchOpen && <AddressSearchModal onSelect={handleAddressSelected} onClose={() => setSearchOpen(false)} />}
    </>
  )
}
