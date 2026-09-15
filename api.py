"""
API 레이어 (FastAPI) — README "다음 단계" 오케스트레이터 위 API 씌우기
--------------------------------------------------------------------------
오늘 이 파일의 목표는 새 비즈니스 로직 추가가 아니라, full_assessment.run_full_assessment()의
인터페이스 계약을 JSON으로 그대로 노출하는 것이다. 로직은 전부 full_assessment.py에 있고,
여기서는 요청/응답 스키마 검증(Pydantic)과 에러 핸들링만 책임진다.

등기부등본 PDF 업로드/OCR은 /assessment와 분리된 별도 엔드포인트(POST /registry/upload)다.
무거운 OCR 연산(tesseract/poppler subprocess 호출)을 메인 진단 로직과 격리하고, OCR
결과를 유저가 눈으로 확인/보정한 뒤에야 최종 /assessment 호출에 실어 보내도록 하기 위함이다
(OCR 오탐지에 대한 사람 확인 버퍼). 그래서 이 엔드포인트는 진단을 실행하지 않고 텍스트와
파싱 결과 미리보기만 반환한다 — 최종 반영은 그 텍스트를 registry_ocr_text에 담아
/assessment를 호출할 때 이뤄진다.

POST /assessment는 계산한 결과를 id로 저장해두고 GET /assessment/{id}로 다시
꺼내볼 수 있게 한다 — 프론트가 결과 화면을 /result/:id 같은 URL로 라우팅해서, 새로고침하거나
링크를 공유해도 같은 결과를 다시 볼 수 있게 하기 위함이다(폼 입력 자체는 재현 대상이 아님).
저장소는 assessment_store.py(SQLite)에 위임한다 — 예전엔 프로세스 메모리 dict에만 있어서
서버 재시작마다 결과가 전부 날아갔는데, 지금은 파일 하나로 재시작에도 살아남는다. 다만
아직은 단일 워커 전제다 — 여러 워커/여러 서버로 스케일하면 SQLite 파일 잠금 경합이 심해질
수 있으니 그때는 Redis 같은 진짜 공유 저장소로 옮겨야 한다(assessment_store.py 참고).

실행: uvicorn api:app --reload
문서: http://127.0.0.1:8000/docs (Swagger UI 자동 생성)
"""

import logging
import os
import tempfile
import uuid
from datetime import date
from typing import Any, Literal

from dotenv import load_dotenv

# address_resolver.py가 모듈 로드 시점에 KAKAO_REST_API_KEY를 읽으므로,
# 아래의 full_assessment(→property_aggregator→address_resolver) import보다 반드시 먼저 실행돼야 한다.
load_dotenv()

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from full_assessment import run_full_assessment
from registry_summary_ocr import find_and_parse_summary_page
from assessment_store import save_assessment, get_assessment as get_stored_assessment

logger = logging.getLogger(__name__)

MAX_REGISTRY_UPLOAD_BYTES = 15 * 1024 * 1024  # 스캔본 PDF 기준 여유있는 상한선

app = FastAPI(
    title="전세/월세 사기 방지 안전진단 API",
    version="0.1.0",
    description="주소·계약조건·등기부 요약을 받아 위험 신호등 등급을 산출한다.",
)


class TaxClearanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submitted: bool
    document_landlord_name: str | None = None
    issue_date: str | None = Field(default=None, description="YYYY-MM-DD")


class OwnershipHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str | None = None
    ownerName: str


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=1, description="유저가 입력한 도로명/지번 주소")
    target_area: float = Field(gt=0, description="대상 전용면적 (㎡)")
    my_deposit: int = Field(gt=0, description="내가 들어갈 보증금 (원 단위)")
    contract_landlord_name: str = Field(min_length=1, description="계약서상 임대인 이름")
    property_type: Literal["apartment", "villa", "officetel", "multi_household"] = "villa"
    as_of: date | None = Field(default=None, description="판단 기준일 (생략 시 오늘)")

    registry_ocr_text: str | None = Field(
        default=None,
        description="등기부등본 '주요 등기사항 요약' 페이지 OCR 원문. "
                    "없으면 깡통전세 위험/임대인 일치 확인이 모두 unknown으로 반환된다.",
    )
    tax_clearance: TaxClearanceInput | None = Field(
        default=None,
        description="아예 생략하면 완납증명서 체크를 건너뛴다. "
                    "submitted=false를 명시적으로 보내는 것과는 다르다(그 경우 warning으로 반영됨).",
    )
    ownership_history: list[OwnershipHistoryEntry] | None = None
    registry_critical_keywords: list[str] | None = Field(
        default=None,
        description="등기부 본문 갑구/을구 치명적 키워드 — 있으면 즉시 danger",
    )
    user_confirmed_violation_building: bool = Field(
        default=False,
        description="유저 자가확인 위반건축물 여부. 건축물대장 API는 이 값을 절대 제공하지 "
                    "않으므로 프론트가 반드시 체크리스트로 물어봐야 한다. True면 danger로 강제.",
    )
    move_in_date: str | None = Field(
        default=None,
        description="잔금(입주)/전입신고 예정일 YYYY-MM-DD. 생략하면 대항력 공백 위험은 "
                    "unknown으로 반환된다.",
    )
    has_fixed_date: bool | None = Field(
        default=None,
        description="확정일자를 받았는지 여부. 생략(null)하면 unknown, false를 명시적으로 "
                    "보내면 '미확보' warning이 반영된다.",
    )


class AssessmentResponse(BaseModel):
    id: str = Field(description="이 결과를 GET /assessment/{id}로 다시 조회할 때 쓰는 식별자")
    overallGrade: Literal["safe", "caution", "warning", "danger", "error"]
    reasons: list[str]
    propertyInfo: dict[str, Any] | None = None
    tenancySafety: dict[str, Any] | None = None
    fraudPatternResult: dict[str, Any] | None = None
    taxClearanceResult: dict[str, Any] | None = None


class RegistryUploadResponse(BaseModel):
    registryOcrText: str = Field(
        description="OCR 원문 그대로 — 유저가 화면에서 확인/수정한 뒤 이 텍스트(수정본)를 "
                    "/assessment의 registry_ocr_text로 그대로 다시 보내면 된다.",
    )
    sourcePage: int = Field(description="PDF 안에서 요약 페이지를 찾은 위치 (1-base)")
    owners: list[dict[str, Any]]
    activeRights: list[dict[str, Any]]
    totalSeniorSecuredAmount: int


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리되지 않은 예외 발생: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요."},
    )


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/assessment", response_model=AssessmentResponse)
def create_assessment(payload: AssessmentRequest) -> dict:
    """
    run_full_assessment()를 그대로 호출한다 (블로킹 I/O라 async def가 아닌 일반 def로 선언 —
    FastAPI가 스레드풀에서 실행해준다). 주소 정규화 실패 등 예상된 실패는
    run_full_assessment 내부에서 이미 overallGrade="error"로 처리되므로 여기서는
    별도 try/except 없이 그대로 반환하고, 예상 밖의 예외만 위 전역 핸들러가 받는다.
    """
    tax_clearance = payload.tax_clearance.model_dump() if payload.tax_clearance else None
    ownership_history = (
        [entry.model_dump() for entry in payload.ownership_history]
        if payload.ownership_history else None
    )

    result = run_full_assessment(
        address=payload.address,
        target_area=payload.target_area,
        my_deposit=payload.my_deposit,
        contract_landlord_name=payload.contract_landlord_name,
        property_type=payload.property_type,
        as_of=payload.as_of,
        registry_summary_text=payload.registry_ocr_text,
        tax_clearance=tax_clearance,
        ownership_history=ownership_history,
        registry_critical_keywords=payload.registry_critical_keywords,
        user_confirmed_violation_building=payload.user_confirmed_violation_building,
        move_in_date=payload.move_in_date,
        has_fixed_date=payload.has_fixed_date,
    )

    assessment_id = uuid.uuid4().hex
    result_with_id = {"id": assessment_id, **result}
    save_assessment(assessment_id, result_with_id)
    return result_with_id


@app.get("/assessment/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: str) -> dict:
    """
    POST /assessment가 방금 만든 결과를 id로 다시 꺼내온다. 프론트가 결과 화면을
    /result/:id로 라우팅해서, 새로고침하거나 링크를 공유해도 같은 결과를 다시 볼 수 있게
    하기 위함이다. 저장소는 SQLite라 서버 재시작에도 살아남는다 — assessment_store.py 참고.
    """
    result = get_stored_assessment(assessment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="해당 진단 결과를 찾을 수 없습니다 (만료되었거나 잘못된 링크일 수 있습니다).")
    return result


def _is_pdf_upload(file: UploadFile) -> bool:
    if file.content_type == "application/pdf":
        return True
    return bool(file.filename) and file.filename.lower().endswith(".pdf")


@app.post("/registry/upload", response_model=RegistryUploadResponse)
def upload_registry_pdf(file: UploadFile = File(...)) -> dict:
    """
    등기부등본 PDF를 받아 '주요 등기사항 요약' 페이지를 찾아 OCR+파싱한 결과를 반환한다.
    이 엔드포인트는 진단을 실행하지 않는다 — 프론트가 registryOcrText를 화면에 보여주고
    유저가 확인/수정하게 한 뒤, 그 텍스트를 /assessment 호출의 registry_ocr_text에 담아
    보내는 게 다음 단계다 (OCR 오탐지에 대한 사람 확인 버퍼).

    find_and_parse_summary_page()가 요약 페이지를 못 찾으면 RuntimeError를 던지는데,
    이건 서버 버그가 아니라 "이 PDF엔 요약 페이지가 없거나 인식이 안 됐다"는 사용자
    입력 문제이므로 500이 아니라 400으로 변환해서 되돌려준다.
    """
    if not _is_pdf_upload(file):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    content = file.file.read()
    if len(content) > MAX_REGISTRY_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"파일이 너무 큽니다 (최대 {MAX_REGISTRY_UPLOAD_BYTES // (1024 * 1024)}MB).",
        )
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = find_and_parse_summary_page(tmp_path)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if tmp_path is not None:
            os.unlink(tmp_path)

    return {
        "registryOcrText": result["_rawOcrText"],
        "sourcePage": result["_sourcePage"],
        "owners": result["owners"],
        "activeRights": result["activeRights"],
        "totalSeniorSecuredAmount": result["totalSeniorSecuredAmount"],
    }
