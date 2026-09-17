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

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import date
from typing import Any, Literal

import sentry_sdk
from dotenv import load_dotenv

# address_resolver.py가 모듈 로드 시점에 KAKAO_REST_API_KEY를 읽으므로,
# 아래의 full_assessment(→property_aggregator→address_resolver) import보다 반드시 먼저 실행돼야 한다.
load_dotenv()

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from full_assessment import run_full_assessment
from registry_summary_ocr import find_and_parse_summary_page
from registry_gapgu_ocr import extract_ownership_history_from_pdf
from assessment_store import (
    cleanup_old_assessments,
    save_assessment,
    get_assessment as get_stored_assessment,
)
from rate_limiter import is_rate_limited

logger = logging.getLogger(__name__)

SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", "development").strip() or "development"
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

MAX_REGISTRY_UPLOAD_BYTES = 15 * 1024 * 1024  # 스캔본 PDF 기준 여유있는 상한선

# 회원가입/로그인이 없는 B2C 무료 버전이라 유저를 구분할 단서가 IP뿐이다 — 봇이
# 반복 호출하면 외부 API(카카오/국토부/VWorld) 쿼터가 먼저 소진되거나 서버가
# 느려져 정상 유저가 피해를 본다(OWASP API4:2023). /assessment는 쿼터 소모형,
# /registry/upload는 CPU 집약적(tesseract/poppler)이라 더 타이트하게 잠근다.
RATE_LIMIT_ASSESSMENT_PER_MINUTE = 5
RATE_LIMIT_REGISTRY_UPLOAD_PER_MINUTE = 3


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

# B2C 무료 버전 비용 방어 스위치. registry_gapgu_ocr.py는 CLOVA_OCR_* 키가 없으면 이미
# no-op으로 빠지지만, 이 플래그는 그것과 별개의 명시적 이중 안전장치다 — 배포 서버에 키가
# 실수로/테스트 목적으로 세팅돼 있어도 B2C 배포에서는 이 값이 false인 한 클로바 API가
# 절대 호출되지 않는다. 나중에 B2B(전문가용) 버전을 띄울 때만 true로 전환한다.
USE_CLOVA_OCR = os.environ.get("USE_CLOVA_OCR", "false").strip().lower() == "true"

app = FastAPI(
    title="전세/월세 사기 방지 안전진단 API",
    version="0.1.0",
    description="주소·계약조건·등기부 요약을 받아 위험 신호등 등급을 산출한다.",
)


async def _periodic_cleanup_expired_assessments() -> None:
    """1시간마다 만료된 assessment를 정리하고, 운영 로그에 실제 삭제 건수를 남긴다."""
    while True:
        try:
            deleted = cleanup_old_assessments(days=30)
            logger.info("assessment cleanup: removed %s expired records from %s", deleted, os.environ.get("ASSESSMENT_DB_PATH", "data/assessments.db"))
        except Exception:
            logger.exception("assessment cleanup loop failed")
        await asyncio.sleep(3600)


@app.on_event("startup")
async def cleanup_expired_assessments_on_startup() -> None:
    """보관기간이 만료된 진단 결과를 제거해 개인정보 처리방침과 구현을 일치시킨다."""
    deleted = cleanup_old_assessments(days=30)
    logger.info("startup assessment cleanup: removed %s expired records", deleted)
    app.state.cleanup_task = asyncio.create_task(_periodic_cleanup_expired_assessments())


@app.on_event("shutdown")
async def shutdown_cleanup_task() -> None:
    task = getattr(app.state, "cleanup_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("assessment cleanup loop cancelled")


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
    eulgu_valid_secured_amount: int | None = Field(
        default=None,
        description="을구 본문 OCR(네이버 클로바)로 직접 뽑은 '말소분 제외 근저당 총액'(원 "
                    "단위, B2B/USE_CLOVA_OCR=true 전용). registry_ocr_text의 요약 페이지 "
                    "합계와 교차검증해 더 큰 쪽을 채택한다(Max Fallback) — 요약 페이지가 "
                    "놓친 근저당이 있어도 위험을 과소평가하지 않기 위함이다.",
    )
    eulgu_has_unparsed_mortgage_amount: bool = Field(
        default=False,
        description="을구 본문에 말소되지 않은 근저당권인데 채권최고액을 인식하지 못한 게 "
                    "있는지(예: 오래된 등기의 한글 숫자 표기 '금일천오백육십만원정'). True면 "
                    "eulgu_valid_secured_amount가 실제보다 적을 수 있다는 뜻이라 caution으로 반영된다.",
    )
    has_rent_right_command: bool = Field(
        default=False,
        description="을구 본문에서 임차권등기명령이 하나라도 발견됐는지. True면 "
                    "registry_critical_keywords에 자동으로 합쳐져 즉시 danger로 강제된다 "
                    "(임차권등기명령은 과거 보증금 미반환으로 법원 명령까지 간 전형적인 "
                    "악성 매물 신호).",
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
    ownershipHistory: list[dict[str, Any]] = Field(
        default_factory=list,
        description="갑구 본문 OCR(네이버 클로바)로 뽑아낸 소유권 이전 이력. "
                    "USE_CLOVA_OCR=false(B2C 기본값)이거나 클로바 키가 없으면 항상 빈 리스트 — "
                    "유저가 화면에서 확인/수정한 뒤 그대로 /assessment의 ownership_history로 "
                    "다시 보내면 사기 패턴 판별에 쓰인다.",
    )
    eulguValidSecuredAmount: int = Field(
        default=0,
        description="을구 본문 OCR로 직접 뽑은 말소분 제외 근저당 총액(원). "
                    "USE_CLOVA_OCR=false(B2C 기본값)이면 항상 0 — 그대로 /assessment의 "
                    "eulgu_valid_secured_amount로 다시 보내면 요약 페이지 합계와 교차검증된다.",
    )
    hasRentRightCommand: bool = Field(
        default=False,
        description="을구 본문에서 임차권등기명령이 발견됐는지. USE_CLOVA_OCR=false(B2C "
                    "기본값)이면 항상 False — 그대로 /assessment의 has_rent_right_command로 "
                    "다시 보내면 즉시 danger로 강제된다.",
    )
    eulguHasUnparsedMortgageAmount: bool = Field(
        default=False,
        description="을구 본문에 말소되지 않은 근저당권인데 채권최고액을 인식 못한 게 있는지. "
                    "USE_CLOVA_OCR=false(B2C 기본값)이면 항상 False — 그대로 /assessment의 "
                    "eulgu_has_unparsed_mortgage_amount로 다시 보내면 caution으로 반영된다.",
    )


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
def create_assessment(payload: AssessmentRequest, request: Request) -> dict:
    """
    run_full_assessment()를 그대로 호출한다 (블로킹 I/O라 async def가 아닌 일반 def로 선언 —
    FastAPI가 스레드풀에서 실행해준다). 주소 정규화 실패 등 예상된 실패는
    run_full_assessment 내부에서 이미 overallGrade="error"로 처리되므로 여기서는
    별도 try/except 없이 그대로 반환하고, 예상 밖의 예외만 위 전역 핸들러가 받는다.

    카카오/국토부/VWorld 쿼터를 소모하므로 IP당 분당 호출 횟수를 제한한다
    (rate_limiter.py 참고).
    """
    if is_rate_limited(_client_ip(request), "assessment", RATE_LIMIT_ASSESSMENT_PER_MINUTE):
        raise HTTPException(
            status_code=429,
            detail="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        )

    tax_clearance = payload.tax_clearance.model_dump() if payload.tax_clearance else None
    ownership_history = (
        [entry.model_dump() for entry in payload.ownership_history]
        if payload.ownership_history else None
    )

    # 임차권등기명령은 registry_critical_keywords와 별도 필드로 받되(프론트에서 "을구
    # 본문 발견 여부"를 명시적인 boolean으로 다루기 편하도록), 판정 로직 자체는 새로
    # 만들지 않고 기존 registry_critical_keywords 경로(있으면 즉시 danger, overall_safety_
    # assessment.py 최우선 규칙)에 그대로 합류시킨다.
    registry_critical_keywords = list(payload.registry_critical_keywords or [])
    if payload.has_rent_right_command and "임차권등기명령" not in registry_critical_keywords:
        registry_critical_keywords.append("임차권등기명령")

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
        registry_critical_keywords=registry_critical_keywords or None,
        eulgu_valid_secured_amount=payload.eulgu_valid_secured_amount,
        eulgu_has_unparsed_mortgage_amount=payload.eulgu_has_unparsed_mortgage_amount,
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
def upload_registry_pdf(request: Request, file: UploadFile = File(...)) -> dict:
    """
    등기부등본 PDF를 받아 '주요 등기사항 요약' 페이지를 찾아 OCR+파싱한 결과를 반환한다.
    이 엔드포인트는 진단을 실행하지 않는다 — 프론트가 registryOcrText를 화면에 보여주고
    유저가 확인/수정하게 한 뒤, 그 텍스트를 /assessment 호출의 registry_ocr_text에 담아
    보내는 게 다음 단계다 (OCR 오탐지에 대한 사람 확인 버퍼).

    find_and_parse_summary_page()가 요약 페이지를 못 찾으면 RuntimeError를 던지는데,
    이건 서버 버그가 아니라 "이 PDF엔 요약 페이지가 없거나 인식이 안 됐다"는 사용자
    입력 문제이므로 500이 아니라 400으로 변환해서 되돌려준다.

    요약 페이지 파싱에 이어, USE_CLOVA_OCR=true일 때만 클로바 OCR로 갑구 본문(소유권 이전
    이력)도 시도한다 (registry_gapgu_ocr.py 참고). B2C 배포 기본값(false)에서는 이 호출
    자체를 건너뛰어 ownershipHistory를 항상 빈 리스트로 반환한다 — 클로바 키가 없어도
    조용히 빈 리스트로 빠지는 것과 별개로, 비용이 드는 API 호출을 원천 차단하기 위함이다.
    이 단계가 꺼져 있거나 실패해도 요약 페이지 파싱 결과 자체는 그대로 반환된다.

    CPU 집약적(tesseract/poppler)이라 /assessment보다 더 타이트하게 IP당 분당 호출
    횟수를 제한한다(rate_limiter.py 참고).
    """
    if is_rate_limited(_client_ip(request), "registry_upload", RATE_LIMIT_REGISTRY_UPLOAD_PER_MINUTE):
        raise HTTPException(
            status_code=429,
            detail="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
        )

    if not _is_pdf_upload(file):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    # 전체를 다 읽은 뒤에야 크기를 확인하면, 큰 파일을 반복 전송하는 것만으로 디스크/
    # 메모리를 소모시키는 자원 고갈 공격(OWASP API4:2023)에 노출된다 — 청크 단위로
    # 읽으면서 상한을 넘는 즉시 중단한다.
    chunk_size = 1024 * 1024
    content = bytearray()
    while True:
        chunk = file.file.read(chunk_size)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_REGISTRY_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"파일이 너무 큽니다 (최대 {MAX_REGISTRY_UPLOAD_BYTES // (1024 * 1024)}MB).",
            )
    content = bytes(content)
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = find_and_parse_summary_page(tmp_path)
        if USE_CLOVA_OCR:
            gapgu_result = extract_ownership_history_from_pdf(
                tmp_path, exclude_pages={result["_sourcePage"]}
            )
        else:
            gapgu_result = {
                "ownershipHistory": [],
                "eulguCriticalKeywords": [],
                "eulguSeniorMortgageAmount": 0,
                "eulguHasUnparsedMortgageAmount": False,
                "pagesProcessed": 0,
                "pagesFailed": [],
            }
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
        "ownershipHistory": gapgu_result["ownershipHistory"],
        "eulguValidSecuredAmount": gapgu_result["eulguSeniorMortgageAmount"],
        "hasRentRightCommand": "임차권등기명령" in gapgu_result["eulguCriticalKeywords"],
        "eulguHasUnparsedMortgageAmount": gapgu_result["eulguHasUnparsedMortgageAmount"],
    }
