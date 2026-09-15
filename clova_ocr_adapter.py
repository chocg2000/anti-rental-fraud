"""
ClovaOcrAdapter — 등기부 본문(갑구/을구) 이미지를 네이버 클로바 OCR(General, V2)로 인식한다.
------------------------------------------------------------------------------------------
등기부 본문 페이지는 위변조 방지 배경무늬 때문에 Tesseract OCR 정확도가 심각하게
떨어진다(registry_summary_ocr.py 모듈 docstring 참고) — 그래서 "주요 등기사항 요약"
페이지만 자체 OCR로 처리하고, 본문(소유권 이전 이력 등)은 확보 경로가 없는 채로 미뤄져
있었다. 이 어댑터는 상용 OCR(클로바)로 본문 페이지를 대신 처리하는 경로를 연다.

⚠️ 미검증 — 아직 실제 Naver Cloud Platform 계정/Secret Key로 호출해본 적이 없다.
요청 스펙(Invoke URL 형식, X-OCR-SECRET 헤더, images[].format/name/data, version="V2",
requestId, timestamp)은 네이버 공식 문서(https://api.ncloud-docs.com/docs/ai-application-service-ocr-ocr)
로 확인했지만, 실제 응답이 그 문서와 정확히 일치하는지는 검증 전이다(이 프로젝트가
MOLIT/VWorld 두 번 다 "문서와 실제 응답이 미묘하게 다르더라"는 걸 겪었으니 여기도
같은 함정을 가정해야 한다). 실제 Secret Key를 받으면 debug_clova_ocr_call.py부터
돌려서 응답을 직접 찍어보고 이 경고를 지울 것.

Invoke URL은 계정마다 다르다(콘솔에서 앱 등록 시 발급되는 고유 경로) — 하드코딩할 수
없으므로 반드시 환경변수로 받는다.
"""

import base64
import os
import time
import uuid

import requests

CLOVA_OCR_INVOKE_URL = os.environ.get("CLOVA_OCR_INVOKE_URL", "")
CLOVA_OCR_SECRET = os.environ.get("CLOVA_OCR_SECRET", "")


def fetch_ocr_result(image_bytes: bytes, image_format: str = "pdf", image_name: str = "registry_page") -> dict:
    """
    등기부 본문 페이지 이미지(또는 PDF 페이지)를 클로바 General OCR(V2)에 보내 인식 결과를
    받는다.

    반환값은 이 프로젝트의 AdapterResult 관례를 따른다:
      {"status": "ok", "data": <클로바 원본 응답 JSON>}
      {"status": "error", "reason": "invalid_request" | "api_down"}

    Args:
        image_bytes: 이미지 또는 PDF 페이지의 바이트
        image_format: "pdf" | "jpg" | "jpeg" | "png" | "tif" | "tiff" (클로바 공식 지원 포맷)
        image_name: 클로바 응답의 images[].name에 그대로 반영되는 식별용 이름(선택)
    """
    if not CLOVA_OCR_INVOKE_URL or not CLOVA_OCR_SECRET:
        # public_price_adapter.py와 동일한 패턴 — 키가 없으면 네트워크 호출 자체를 하지
        # 않고 안전하게 no-op으로 빠진다.
        return {"status": "error", "reason": "invalid_request"}

    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "lang": "ko",
        "images": [
            {
                "format": image_format,
                "name": image_name,
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        ],
    }
    headers = {
        "X-OCR-SECRET": CLOVA_OCR_SECRET,
        "Content-Type": "application/json",
    }

    try:
        res = requests.post(CLOVA_OCR_INVOKE_URL, json=payload, headers=headers, timeout=20)
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "api_down"}
    except requests.exceptions.RequestException:
        return {"status": "error", "reason": "api_down"}

    if res.status_code != 200:
        return {"status": "error", "reason": "invalid_request"}

    try:
        data = res.json()
    except ValueError:
        return {"status": "error", "reason": "api_down"}

    # 문서상 images[0].inferResult가 "SUCCESS"가 아니면 인식 자체가 실패한 것 —
    # 크래시 대신 정직하게 error로 알린다.
    images = data.get("images") or []
    if not images or images[0].get("inferResult") != "SUCCESS":
        return {"status": "error", "reason": "invalid_request"}

    return {"status": "ok", "data": data}
