import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import Step1Address from './steps/Step1Address'
import Step2Documents from './steps/Step2Documents'
import ResultRoute from './routes/ResultRoute'
import { requestAssessment } from './lib/api'
import { loadSessionState, saveSessionState, clearSessionState } from './lib/sessionState'

const initialForm = {
  address: '',
  addressDetail: '',
  targetArea: '',
  myDeposit: '',
  contractLandlordName: '',
  propertyType: 'villa',
  moveInDate: '',
  privacyConsent: false,
}

const initialDocuments = {
  violationChoice: null,
  uploadState: 'idle',
  uploadError: null,
  registryOcrText: '',
  registryPreview: null,
  taxChoice: null,
  taxDocLandlordName: '',
  taxIssueDate: '',
  fixedDateChoice: null,
}

function isStep1Complete(form) {
  return (
    form.address.trim() !== '' &&
    Number(form.targetArea) > 0 &&
    Number(form.myDeposit) > 0 &&
    form.contractLandlordName.trim() !== '' &&
    form.privacyConsent === true
  )
}

// 업로드 중이던 상태를 새로고침 후 그대로 복원하면 응답이 영영 안 올 스피너만 남으므로
// 불러올 때 idle로 되돌린다 (재업로드는 유저가 다시 누르면 됨).
function sanitizeLoadedDocuments(loaded) {
  return loaded.uploadState === 'uploading' ? { ...loaded, uploadState: 'idle' } : loaded
}

function AppRoutes() {
  const navigate = useNavigate()
  const [form, setForm] = useState(() => loadSessionState('form', initialForm))
  const [documents, setDocuments] = useState(() => sanitizeLoadedDocuments(loadSessionState('documents', initialDocuments)))
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    saveSessionState('form', form)
  }, [form])

  useEffect(() => {
    saveSessionState('documents', documents)
  }, [documents])

  function buildPayload() {
    const fullAddress = [form.address.trim(), form.addressDetail.trim()].filter(Boolean).join(' ')
    const payload = {
      address: fullAddress,
      target_area: Number(form.targetArea),
      my_deposit: Number(form.myDeposit),
      contract_landlord_name: form.contractLandlordName.trim(),
      property_type: form.propertyType,
      user_confirmed_violation_building: documents.violationChoice === 'violation',
    }
    if (form.moveInDate) {
      payload.move_in_date = form.moveInDate
    }
    if (documents.fixedDateChoice === 'yes') {
      payload.has_fixed_date = true
    } else if (documents.fixedDateChoice === 'no') {
      payload.has_fixed_date = false
    }
    if (documents.uploadState === 'uploaded' && documents.registryOcrText.trim() !== '') {
      payload.registry_ocr_text = documents.registryOcrText
    }
    if (documents.registryPreview?.ownershipHistory?.length > 0) {
      payload.ownership_history = documents.registryPreview.ownershipHistory
    }
    if (documents.registryPreview?.eulguValidSecuredAmount > 0) {
      payload.eulgu_valid_secured_amount = documents.registryPreview.eulguValidSecuredAmount
    }
    if (documents.registryPreview?.eulguHasUnparsedMortgageAmount) {
      payload.eulgu_has_unparsed_mortgage_amount = true
    }
    if (documents.registryPreview?.hasRentRightCommand) {
      payload.has_rent_right_command = true
    }
    if (documents.taxChoice === 'yes') {
      payload.tax_clearance = {
        submitted: true,
        document_landlord_name: documents.taxDocLandlordName.trim() || null,
        issue_date: documents.taxIssueDate || null,
      }
    } else if (documents.taxChoice === 'no') {
      payload.tax_clearance = { submitted: false }
    }
    return payload
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const data = await requestAssessment(buildPayload())
      navigate(`/result/${data.id}`, { state: { result: data } })
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function handleRestart() {
    setForm(initialForm)
    setDocuments(initialDocuments)
    clearSessionState('form')
    clearSessionState('documents')
    navigate('/step1')
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/step1" replace />} />
      <Route path="/step1" element={<Step1Address form={form} onChange={setForm} onNext={() => navigate('/step2')} />} />
      <Route
        path="/step2"
        element={
          isStep1Complete(form) ? (
            <Step2Documents
              documents={documents}
              onChange={setDocuments}
              onSubmit={handleSubmit}
              submitting={submitting}
              submitError={submitError}
              onDismissSubmitError={() => setSubmitError(null)}
            />
          ) : (
            <Navigate to="/step1" replace />
          )
        }
      />
      <Route path="/result/:id" element={<ResultRoute onRestart={handleRestart} />} />
      <Route path="*" element={<Navigate to="/step1" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-svh items-start justify-center bg-gray-100 sm:items-center sm:py-8">
        <AppRoutes />
      </div>
    </BrowserRouter>
  )
}
