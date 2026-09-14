# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

전세/월세 계약 전 주소·계약조건을 입력하면 등기부등본·실거래가·건축물대장·공시가격을
종합해 위험도(안전/주의/경고/위험)를 알려주는 안전진단 앱. Python/FastAPI 백엔드 +
React/Vite 프론트엔드. Roadmap: 1단계 B2C 무료 → 2단계 공인중개사 영업 → 3단계 SaaS/API.

`README.md`가 이 프로젝트의 실질적인 작업 로그다 — 세션 간 "지금까지 뭘 했고 뭐가
남았는지"를 공유하는 용도로 계속 갱신되고 있으니, 새 세션에서는 먼저 그 파일부터 읽을 것.
알려진 버그/설계 결정/미해결 이슈가 전부 거기 기록돼 있다.

## Commands

Backend (project root):
```bash
pip install -r requirements.txt
uvicorn api:app --reload                      # http://127.0.0.1:8000/docs (Swagger UI)
python run_all_tests.py                       # 전체 test_*.py 자동 탐색 후 실행
python -m unittest discover -p "test_*.py"    # 동일 (더 짧은 요약 출력)
python -m unittest test_api -v                # 파일 하나만
python -m unittest test_api.TestHealthCheck.test_health_returns_ok  # 테스트 하나만
```

Frontend (`frontend/`):
```bash
npm install
npm run dev      # http://localhost:5173, /api/* 는 vite.config.js 프록시로 127.0.0.1:8000에 전달
npm run build
npm run lint      # oxlint
```

Docker (스캐폴딩 있음, **빌드 미검증** — 이 개발 환경에 Docker가 없어 한 번도 안 돌려봄):
```bash
docker compose up --build   # frontend: localhost:5173, backend: localhost:8000
```

로컬 실행 시 `.env`가 필요하다 (`.env.example` 참고): `KAKAO_REST_API_KEY`,
`MOLIT_SERVICE_KEY`가 있어야 실거래가/건축물대장/주소 조회가 실제로 동작한다. 없으면
해당 소스는 조용히 `"error"`/`"unavailable"` status로 폴백하고 앱 자체는 안 죽는다
(아래 "부분 실패" 원칙 참고). Windows에서 `POST /registry/upload`(OCR)를 실제로 돌리려면
`TESSERACT_CMD`/`PDFTOPPM_CMD`/`PDFINFO_CMD`도 필요 — Ubuntu/Docker는 `apt-get`
설치본이 PATH에 잡히므로 불필요.

## Architecture

### 데이터 흐름 (여러 파일을 함께 봐야 이해되는 부분)

```
주소 입력
  ├─ address_resolver.py (카카오 로컬 REST API) → 법정동코드/PNU/좌표
  ├─ real_transaction_price_adapter.py (국토부 실거래가) ─┐
  ├─ building_register_adapter.py (국토부 건축HUB) ───────┼─ property_aggregator.py가
  └─ public_price_adapter.py (VWorld 공시가격, 스텁) ─────┘  3개를 병렬 호출 + 부분실패 허용
        └─ market_price_estimator.py가 실거래가로 시세 추정, 없으면 공시가격 폴백

등기부등본 PDF 업로드
  ├─ registry_summary_ocr.py (tesseract/poppler subprocess 직접 호출, 파이썬 래퍼 안 씀)
  └─ registry_summary_parser.py → 소유자, 선순위채권(근저당+전세권) 합계

계약 조건 (보증금·임대인 이름·완납증명서)
  ├─ tenancy_safety_rules.py → 깡통전세 위험(LTV) + 임대인 일치 검증
  ├─ tax_clearance_check.py → 완납증명서 체크
  └─ fraud_pattern_rules.py → 신축빌라+소유주변경 패턴

           ↓ 전부 모아서
overall_safety_assessment.py → 최종 신호등 등급(safe/caution/warning/danger)
           ↓
full_assessment.py (오케스트레이터) → 위 전체를 순서대로 호출, 이것만 부르면 등급까지 나옴
           ↓
api.py (FastAPI) → POST/GET /assessment, POST /registry/upload, GET /health
           ↓
frontend/ (React Router: /step1 → /step2 → /result/:id)
```

프로젝트 루트에 서브폴더 없이 `.py` 파일이 전부 평평하게 있다 (`frontend/`만 예외).

### 핵심 설계 원칙 — 코드 고칠 때 반드시 지킬 것

- **부분 실패 허용, 크래시 금지.** 모든 어댑터는 예외를 던지지 않고
  `{"status": "ok"/"not_found"/"error", ...}` 형태로 정직하게 반환한다. 없는 데이터를
  억지로 채우지 않는다 — 예: 실거래가 없으면 `marketPrice: null, confidence: "unavailable"`
  이지 대충 추정치를 넣지 않는다. `address_resolver.py`만 예외 — 주소 자체가 틀리면
  뒤의 모든 조회가 무의미하므로 `AddressResolutionError`를 던지고
  `property_aggregator.py`가 이를 `PropertyAggregationError`로 바꿔 상위로 전파한다.
- **단위 불일치에 주의**: `market_price_estimator.py`/`property_aggregator.py`의
  `marketPrice`는 **만원** 단위인데 `tenancy_safety_rules.py`는 **원** 단위를 기대한다.
  변환은 `full_assessment.py`에서만 한다 — 실제로 이 변환을 빼먹어서 시세가 1만 배
  작게 들어가는 버그가 났던 적이 있다.
- **위반건축물 여부는 API로 확인 불가** (국토부가 공식적으로 비공개). 반드시 유저
  자가확인(`user_confirmed_violation_building`)으로 받아야 하고, `True`면 무조건
  `danger`로 강제된다.
- **등기부 OCR은 요약 페이지가 주력 경로.** 본문(갑구/을구)은 위변조 방지 배경무늬 때문에
  OCR 정확도가 낮아서, PDF 뒤에서부터 "주요 등기사항 요약" 페이지를 찾아 그것만 OCR한다
  (`registry_summary_ocr.py`). `registry_parser.py`(본문 갑구/을구 파싱)는 로직은
  완성됐지만 실사용 데이터 확보 경로가 아직 없다.
- **`public_price_adapter.py`(VWorld)는 미검증 스텁**이다 — vworld.kr 접속 제한으로
  실제 응답을 한 번도 못 봤다. `property_aggregator.py`에는 이미 연결돼 있지만, 키가
  없으면 네트워크 호출 자체를 안 하고 즉시 `error`를 반환하도록 만들어서 지금은
  안전하게 no-op이다. 실제 키를 받으면 `_parse_response()`를 실제 응답 구조에 맞게
  다시 써야 한다 (README의 "VWorld 공시가격 연동 스텁" 섹션에 순서 정리돼 있음).
- **`registry_summary_ocr.py`는 pytesseract/pdf2image 같은 파이썬 래퍼를 안 쓴다** —
  `tesseract`/`pdftoppm`/`pdfinfo`를 subprocess로 직접 호출한다. `subprocess.run(...,
  text=True)`에 `encoding="utf-8", errors="replace"`를 반드시 명시할 것 — 안 하면
  Windows에서 플랫폼 기본 인코딩(cp949)으로 디코딩하려다 크래시한다(실제로 겪은 버그).
- **개별 모듈 로직 먼저 → 실키로 검증** 순서로 만들어왔다. `test_*.py`는 전부 모킹된
  순수 유닛 테스트라 API 키 없이 항상 통과해야 한다. 실제 키로 검증할 때는 별도의
  `run_real_*.py`/`debug_*.py` 스크립트를 쓴다(예: `run_real_transaction_test.py`,
  `debug_molit_call.py`) — 새 외부 API를 붙일 때도 이 패턴을 따를 것.

### 프론트엔드

- `App.jsx`가 `react-router-dom`으로 `/step1`(주소·계약조건) → `/step2`(서류·자가진단) →
  `/result/:id`(결과)를 라우팅한다. Step1/Step2의 폼 상태는 `src/lib/sessionState.js`로
  sessionStorage에 저장(새로고침 대응), 결과는 백엔드의 `GET /assessment/{id}`로
  재조회 가능(새로고침·링크공유 대응) — 이 둘은 서로 다른 계층이라 폼은 서버에 저장 안 함.
- `src/lib/api.js`가 `/api` 프리픽스로 백엔드를 호출한다 — dev 서버는
  `vite.config.js`의 프록시가, Docker 배포는 `frontend/nginx.conf`가 `/api/`를
  백엔드로 라우팅한다(둘 다 같은 역할, 설정 위치만 다름).
- Step2의 등기부 PDF 업로드는 `POST /registry/upload`(진단 실행 안 함, 파싱 미리보기만
  반환) → 유저가 OCR 텍스트를 화면에서 수정 → 최종 `POST /assessment`의
  `registry_ocr_text`에 그 텍스트를 실어 보낸다. 소유자 이름 등은 참고용 읽기 전용
  표시일 뿐 실제로 서버에 반영되는 건 `registry_ocr_text` 원문 하나뿐이다.
- `POST /assessment`가 계산한 결과는 백엔드 프로세스 메모리에 `id`로 저장된다
  (`api.py`의 `_ASSESSMENT_STORE`) — 서버 재시작하면 사라지는 프로토타입 수준.

### 백엔드 API 계약

- `api.py`의 Pydantic 모델은 `extra="forbid"` — 계약에 없는 필드를 보내면 422.
- 주소 정규화 실패처럼 "예상된" 실패는 HTTP 200 + `overallGrade="error"`로 내려간다
  (요청 자체는 유효하므로). 예상 못 한 예외만 전역 핸들러가 500으로 변환한다.
