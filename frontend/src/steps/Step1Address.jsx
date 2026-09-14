import { useState } from 'react'
import ScreenShell from '../components/ScreenShell'
import AddressSearchModal from '../components/AddressSearchModal'

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
    form.contractLandlordName.trim() !== ''

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
      </div>
    </ScreenShell>
    {searchOpen && <AddressSearchModal onSelect={handleAddressSelected} onClose={() => setSearchOpen(false)} />}
    </>
  )
}
