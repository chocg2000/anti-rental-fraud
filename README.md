# 전세/월세 사기 방지 앱 — 프로젝트 현황

> 이 파일은 claude.ai 채팅과 VSCode의 Claude Code, 두 세션을 오가며 작업할 때
> "지금까지 뭘 했고, 뭐가 남았는지"를 공유하기 위한 문서입니다.
> **작업 세션을 마칠 때마다 이 파일의 "최근 업데이트"와 "다음 단계"를 갱신해주세요.**

---

## 컨셉

전세/월세 계약 전, 주소와 계약 조건(보증금·임대인 이름)을 입력하면
등기부등본·실거래가·건축물대장 데이터를 종합해 위험도(안전/주의/경고/위험)를
알려주는 1단계 B2C 무료 웹/앱. (로드맵: 1단계 B2C 무료 → 2단계 공인중개사 영업 → 3단계 SaaS/API)

## 아키텍처 (데이터 흐름)

```
주소 입력
  ├─ address_resolver.py (카카오 API) → 법정동코드/PNU/좌표
  ├─ real_transaction_price_adapter.py (국토부) → 실거래가
  │     └─ market_price_estimator.py → 시세 추정 (중위값, 같은동→자치구 확대, 공시가격 폴백)
  └─ building_register_adapter.py (국토부 건축HUB) → 건물정보, 근생빌라 탐지
        └─ property_aggregator.py 가 위 3개를 병렬 호출 + 부분실패 허용

등기부등본 PDF 업로드
  ├─ registry_summary_ocr.py → PDF에서 '요약 페이지' 자동 탐지 + OCR
  └─ registry_summary_parser.py → 소유자, 선순위채권(근저당+전세권) 합계 파싱
  (registry_parser.py: 본문 갑구/을구 파싱 로직은 완성됐으나, 실제 데이터 확보
   경로는 미해결 — 아래 "미해결 이슈" 참고)

계약 조건 입력 (보증금, 임대인 이름, 완납증명서 여부)
  ├─ tenancy_safety_rules.py → 깡통전세 위험 + 임대인 일치 검증
  ├─ tax_clearance_check.py → 완납증명서 제출여부/명의/발급일 체크
  └─ fraud_pattern_rules.py → 신축빌라+소유주변경 패턴 (이력 데이터 필요, 아래 참고)

           ↓ 위 결과를 전부 모아서
overall_safety_assessment.py → 최종 신호등 등급(safe/caution/warning/danger)

           ↑ 위 전체 흐름을 하나로 묶는 오케스트레이터
full_assessment.py → run_full_assessment(address, target_area, my_deposit,
    contract_landlord_name, ...) 하나만 호출하면 등급까지 나옴

           ↑ 이걸 JSON으로 노출하는 API 레이어
api.py (FastAPI) → POST /assessment (결과를 id로 인메모리 저장) , GET /health
                   GET /assessment/{id} → 저장된 결과 재조회 (새로고침/링크공유 대응)
                   POST /registry/upload → PDF 업로드 → OCR+파싱 미리보기만 반환
                   (진단 실행 안 함 — 유저가 확인/보정 후 그 텍스트로 /assessment 호출)

           ↑ 이걸 호출하는 프론트엔드 (react-router-dom 라우팅)
frontend/ → /step1(Step1Address) → /step2(Step2Documents) → /result/:id(ResultRoute→Step3Result)
    Step1/Step2 입력값은 sessionStorage에도 저장 — 새로고침해도 폼이 안 날아감
    /result/:id는 새로고침·직접 접속 시 GET /assessment/:id로 백엔드에서 다시 불러옴
```

## 실행

백엔드:
```bash
pip install -r requirements.txt
uvicorn api:app --reload      # http://127.0.0.1:8000/docs 에서 Swagger UI로 바로 테스트 가능
```

프론트엔드 (별도 터미널):
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 — /api/* 요청은 vite.config.js 프록시로
                               # http://127.0.0.1:8000 (백엔드)에 전달됨. 백엔드를 먼저 띄울 것.
```

## 테스트

```bash
python run_all_tests.py   # 전체 test_*.py 자동 탐색 후 실행
```
2026-09-13 기준 **146개 테스트 전부 통과**.

## 완료된 모듈

| 파일 | 역할 | 검증 상태 |
|---|---|---|
| `address_resolver.py` | 주소 → 법정동코드/PNU (카카오 API) | ✅ 실제 키로 검증 |
| `real_transaction_price_adapter.py` | 국토부 실거래가 조회 | ✅ 실제 데이터로 검증, 버그 2개 수정 이력 있음 |
| `market_price_estimator.py` | 시세 추정 (동→구 확대, 공시가격 폴백 포함) | ✅ 실제 데이터로 검증 |
| `building_register_adapter.py` | 건축물대장(건축HUB) 조회, 근생빌라 탐지 | ✅ 실제 데이터로 검증, 버그 3개 수정 이력 있음 |
| `property_aggregator.py` | 실거래가/건축물대장/공시가격 병렬 호출 + 부분실패 허용 | ✅ |
| `public_price_adapter.py` | 브이월드 공동주택가격속성조회 (`ned/data/getApartHousingPriceAttr`) | ✅ 실제 성공 응답으로 검증 (아래 참고) |
| `registry_parser.py` | 등기부 본문(갑구/을구) 파싱 로직 | ✅ 로직 완성 (실제 데이터 확보 경로는 미해결) |
| `registry_summary_parser.py` / `registry_summary_ocr.py` | 등기부 요약 페이지 OCR+파싱 | ✅ 실제 PDF로 엔드투엔드 검증 (Windows 포함) |
| `fraud_pattern_rules.py` | 신축빌라+소유주변경 탐지 | ✅ 로직 완성 (이력 데이터 확보 경로는 미해결) |
| `tenancy_safety_rules.py` | 깡통전세 위험 + 임대인 일치(법인/신탁/공유자 구분) | ✅ |
| `tax_clearance_check.py` | 완납증명서 체크 | ✅ |
| `overall_safety_assessment.py` | 종합 신호등 등급 산출 | ✅ |
| `test_e2e_pipeline.py` / `e2e_fixtures.py` | 실제 데이터 스냅샷 기반 엔드투엔드 회귀 테스트 | ✅ |
| `full_assessment.py` | 위 9개 모듈을 실제 흐름대로 호출하는 오케스트레이터 (`run_full_assessment`) | ✅ 배선 테스트 10개 통과 |
| `api.py` | FastAPI 레이어 — `POST/GET /assessment`, `POST /registry/upload`, `GET /health` | ✅ 계약 테스트 20개 통과 |
| `frontend/` | React+Vite+Tailwind 실제 화면, react-router-dom 라우팅 (Step1/2/Result) | ✅ 백엔드와 실제 연동 확인 (아래 참고) |

## 알려진 사실 / 설계 결정 (실제 데이터로 검증하며 확정된 것들)

- **위반건축물 여부는 API로 자동화 불가능** (국토부가 공식적으로 비공개, 분쟁조정 사례로 확인됨)
  → 유저 자기확인 체크리스트 항목으로 재분류 필요
- **등기부등본 PDF는 이미지 스캔본**이라 OCR 필요. 본문(갑구/을구)은 배경무늬 때문에
  OCR 정확도가 낮지만, **"주요 등기사항 요약" 페이지는 배경무늬가 적어 정확도가 훨씬 좋음**
  → 그래서 요약 페이지 기반 파서(`registry_summary_parser.py`)를 주력으로 채택
- **전세권설정도 근저당권처럼 선순위채권으로 계산해야 함** (실제 문서로 발견, 요약 페이지가
  근저당권+전세권을 같이 보여줘서 자연스럽게 해결됨)
- 완납증명서는 체납액 자체가 안 적힌 서류라, "체납액 합산"이 아니라
  "제출여부/명의일치/발급일 최신성" 체크로 스코프 조정함
- **`property_aggregator`의 marketPrice(만원 단위)와 `tenancy_safety_rules`가 기대하는
  금액(원 단위)이 서로 다른 단위였음** — 오케스트레이터를 만들면서 발견. 변환 안 하면
  시세가 1만 배 작게 들어가 깡통전세 위험 판정이 완전히 틀어짐. `full_assessment.py`에서만
  변환 처리하고, 개별 모듈은 그대로 둠.
- **`address_resolver.py`가 `KAKAO_REST_API_KEY` 미설정 시 크래시하던 버그 수정** — 실제로
  프론트엔드를 붙여서 서버를 처음 띄워보다가 발견됨. 기존엔 키가 없으면 한글이 포함된
  플레이스홀더 문자열("여기에_발급받은_REST_API_키를_입력")을 그대로 HTTP `Authorization`
  헤더에 넣었는데, HTTP 헤더는 latin-1만 허용해서 `UnicodeEncodeError`가 `AddressResolutionError`로
  안 잡히고 그대로 500으로 터졌음. 기본값을 `None`으로 바꿔 정상적으로 401 → `AddressResolutionError`
  → `overallGrade="error"` 경로를 타도록 수정. (지금까지 전 구간이 모킹 테스트였어서 이 경로를
  아무도 실제로 밟아본 적이 없었음 — 실제 통합 실행이 왜 중요한지 보여주는 사례.)
- **공공데이터포털(data.go.kr) 키는 계정당 하나(일반 인증키)를 여러 API에 공통으로 씀** —
  API마다 별도 키가 아니라 API별로 "활용신청" 승인만 따로 받으면 됨. `MOLIT_SERVICE_KEY` 하나로
  실거래가(`RTMSDataSvcAptTradeDev`)와 건축HUB(`BldRgstHubService`) 둘 다 인증.
- **`SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(reason code 30)가 떴을 때 승인 상태가 멀쩡해도
  키 값 자체가 틀렸을 수 있음** — 실제로 마이페이지에서 인증키를 다시 복사해서 넣었더니
  해결됨(87자→88자로 길이가 달랐음, 최초 값이 잘못 복사됐던 것). 이 에러가 뜨면 활용신청
  승인 여부보다 키 값 자체(복사 버튼으로 재복사)부터 의심할 것.

## 실제 API 키로 검증 완료 (2026-09-13)

로컬 `.env`(git 미추적)에 `KAKAO_REST_API_KEY` + `MOLIT_SERVICE_KEY`를 설정하고
`POST /assessment`를 프론트엔드→프록시→백엔드 전 구간으로 실제 호출해 확인함:
- 카카오 주소 검색: 실제 지번주소/PNU/좌표 정상 반환
- 국토부 실거래가: `resultCode 000`, 실제 거래 데이터 기준 시세 산출 (신뢰도 "high")
- 건축HUB 건축물대장: `resultCode 00`, 실제 건물 정보(용도/사용승인일 등) 반환
- 위 세 값을 조합해 `overallGrade`까지 실제로 산출되는 것 확인 (예: 업무시설 건물 →
  `nonResidentialUseRisk` 플래그 → `warning` 등급)

이제 남은 미확보 데이터는 등기부등본(유저 PDF 업로드 필요)과 공시가격(vworld, 아래 이슈 1번)뿐.

## Tesseract/Poppler 실환경 검증 완료 (2026-09-14, Windows)

관리자 권한 없이 포터블 방식으로 설치 후, 실제 등기부등본 PDF(프로젝트 루트의
`등기부등본_내아파트.pdf`, `.gitignore`로 제외된 개인 파일)로 `POST /registry/upload`까지
전 구간 검증 완료.

**설치 방법** (choco는 관리자 권한이 없어 "installed 0/0 packages"로 실패 — 포터블
방식으로 전환):
- Poppler: [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows)
  릴리스 zip을 `tools/poppler/`에 압축 해제 (설치 불필요, 그냥 실행파일)
- Tesseract: [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract) 설치파일을
  `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-` 옵션으로 조용히 설치 (`/CURRENTUSER`
  플래그를 같이 주면 GUI 다이얼로그가 뜨면서 멈춤 — 빼야 진짜 조용히 진행됨). 기본 개인
  설치 경로(`%LOCALAPPDATA%\Programs\Tesseract-OCR`)에 관리자 권한 없이 설치됨.
- `tools/`는 `.gitignore` 처리 — 바이너리를 git에 올리지 않고, `.env`의 경로로만 참조.

**코드 변경**: `registry_summary_ocr.py`가 원래 `pdfinfo`/`pdftoppm`/`tesseract`를 PATH에
있다고 가정하고 바로 호출했는데(pytesseract/pdf2image 같은 파이썬 래퍼는 애초에 안 씀 —
subprocess로 CLI 직접 호출), Windows는 이 실행파일들이 PATH에 자동 등록 안 되는 경우가
많아서 `TESSERACT_CMD`/`PDFTOPPM_CMD`/`PDFINFO_CMD` 환경변수로 전체 경로를 오버라이드할
수 있게 고침 (기본값은 그대로 bare 명령어라 Ubuntu 배포 환경엔 영향 없음).

**실제로 두 개의 새 버그를 발견/수정함**:
1. **인코딩 버그** — `subprocess.run(..., text=True)`에 `encoding`을 명시 안 하면 플랫폼
   기본 인코딩을 쓰는데, Windows는 그게 cp949라 tesseract/poppler의 UTF-8 출력을 디코딩
   하다 `UnicodeDecodeError`로 크래시함. 지금까지 이 경로가 리눅스/WSL에서만 검증됐어서
   (기본 로케일이 UTF-8) 안 드러났던 버그. `encoding="utf-8", errors="replace"`로 수정 —
   `errors="replace"`가 필요한 이유는 포플러 Windows 빌드가 콘솔 출력 중 일부(파일 경로 등)를
   로컬 코드페이지로 섞어 내보내기도 해서, 순수 UTF-8 강제 디코딩만으로는 다른 지점에서
   또 깨졌기 때문 (우리가 정규식으로 뽑는 "Pages: N"은 항상 ASCII라 무관하게 안전함).
2. **`.env` 편집 실수** — 기존 `.env` 파일 끝에 줄바꿈이 없는 상태에서 새 줄을 이어붙였다가
   `MOLIT_SERVICE_KEY` 값 뒤에 `TESSERACT_CMD=...`가 그대로 붙어버려 키가 오염된 적이 있음.
   `.env`를 스크립트로 append할 땐 파일이 개행으로 끝나는지 먼저 확인할 것.

**검증 결과**: OCR이 요약 페이지(9번째 페이지)를 정확히 찾았고, 파싱된 값(소유자 "조춘근",
전세권 300,000,000원)이 그동안 `e2e_fixtures.py`에서 써온 실제 야탑동 데이터와 정확히
일치함 — 이 PDF가 바로 그 원본이었음. 터미널에 한글이 깨져 보이는 건 이 Windows 콘솔
(cp949)의 표시 문제일 뿐, JSON 응답 자체는 UTF-8 바이트 단위로 검증해서 정확함을 확인함.

## 미해결 이슈 (다음 세션에서 이어갈 것들)

1. ~~공시가격 API 미연결~~ → **2026-09-15 연동 완료** (아래 "VWorld 공시가격 연동" 섹션
   참고) — 단, vworld.kr API 서버 자체가 이 개발 머신(싱가포르 IP)에서 계속 불안정해서
   (연결 끊김 또는 502) 실제 검증은 지인의 브라우저를 거쳐서 했다. 이 머신에서 vworld를
   직접 못 두드리는 문제 자체는 해결 안 됐으니, 배포 서버(국내 리전)에서 최종 확인 필요.
2. **등기부 본문(갑구) 소유권 이전 이력 확보 경로 미해결** — `registry_parser.py`와
   `fraud_pattern_rules.py`(신축빌라+소유주변경 룰) 로직은 완성됐지만, 본문 OCR 정확도가
   낮아서 실제 이력 데이터를 안정적으로 못 가져오는 상태. 상용 OCR API(네이버 CLOVA,
   Upstage 등) 도입 검토 필요.
3. ~~PDF 업로드 서버에 tesseract/poppler 미설치~~ → **2026-09-14 실환경(Windows) 검증
   완료** (아래 "Tesseract/Poppler 실환경 검증" 섹션 참고). 다만 이건 개발 머신(Windows)
   검증이고, 실제 배포 서버(Ubuntu/Debian 예정)에서는 `sudo apt-get install tesseract-ocr
   tesseract-ocr-kor poppler-utils`로 다시 한번 확인 필요 — PATH 자동 등록되는 환경이라
   `.env`의 `TESSERACT_CMD` 등은 안 넣어도 기본값(`"tesseract"`)으로 바로 동작할 것으로 예상.

## `full_assessment.py` 인터페이스 계약 (오케스트레이터 완성, 2026-09-13)

`run_full_assessment(address, target_area, my_deposit, contract_landlord_name, ...)` 하나로
전체 흐름(주소 정규화 → 시세/건축물대장 → 등기부 요약 → 임대인/깡통전세 검증 → 사기패턴 →
완납증명서 → 종합등급)을 실행한다.

- **필수**: `address`, `target_area`, `my_deposit`(원 단위), `contract_landlord_name`
- **선택**: `registry_summary_text`(없으면 깡통전세/임대인일치 둘 다 "unknown"),
  `tax_clearance`(아예 안 주면 체크 자체를 건너뜀 — `submitted: False`를 명시적으로 주는 것과 다름),
  `ownership_history`, `registry_critical_keywords`, `property_type`
- **유저 자가확인 필수**: `user_confirmed_violation_building` — 건축물대장 API가 절대
  안 주는 값이라 True로만 들어오면 무조건 danger로 강제됨
- **출력**: `overallGrade`(safe/caution/warning/danger/**error**) + `reasons` +
  `propertyInfo`/`tenancySafety`/`fraudPatternResult`/`taxClearanceResult` 원본 그대로 포함
  (프론트가 세부 사유를 보여줘야 할 때 재조합할 필요 없게 함). 주소 정규화 자체가
  실패하면 나머지 조회 없이 `overallGrade="error"`로 즉시 반환.
- 테스트: `test_full_assessment.py` (10개, 배선/단위변환/부재값 처리만 검증 — 개별 룰
  로직은 각 모듈 자체 테스트가 이미 커버함)

## `api.py` 인터페이스 계약 (FastAPI 레이어 완성, 2026-09-13)

`POST /assessment`가 `full_assessment.run_full_assessment()`를 그대로 JSON으로 노출한다
(새 비즈니스 로직 없음 — 요청/응답 스키마 검증과 에러 핸들링만 담당).

- Request body 필드명은 `run_full_assessment`의 Python 파라미터명과 1:1 대응 (스네이크케이스),
  단 등기부 텍스트만 `registry_ocr_text`로 명명(내부적으로 `registry_summary_text`에 매핑).
- `extra="forbid"` — 계약에 없는 필드를 보내면 조용히 무시되지 않고 422로 바로 드러남.
- `target_area > 0`, `my_deposit > 0`, `property_type`은 4개 값 중 하나만 허용 등 Pydantic
  단에서 검증 — 잘못된 요청은 비즈니스 로직까지 가지 않고 422에서 걸러짐.
- 주소 정규화 실패 같은 "예상된" 실패는 HTTP 200 + `overallGrade="error"`로 내려감
  (요청 자체는 유효했으므로). 예상 못 한 예외만 전역 핸들러가 500 + 안전한 메시지로 변환
  (스택트레이스는 서버 로그에만 남고 응답 바디에는 안 실림).
- 테스트: `test_api.py` (20개 — 요청 검증, 필드 매핑, 에러 핸들링, 결과 재조회까지 검증)

### `GET /assessment/{id}` — 진단 결과 재조회 (2026-09-14 추가)

`POST /assessment`가 계산한 결과를 응답에 `id`를 붙여서 그대로 인메모리 딕셔너리
(`_ASSESSMENT_STORE`)에 저장해두고, 같은 `id`로 다시 꺼내볼 수 있게 한다. 프론트가 결과
화면을 `/result/:id`로 라우팅해서, 새로고침하거나 링크를 다른 사람에게 공유해도 같은
결과를 다시 보여줄 수 있게 하기 위함 — 반대로 Step1/Step2의 "입력 폼"은 서버에 저장할
이유가 없어서(재현 대상이 아님) 그건 프론트 쪽 sessionStorage로만 처리한다(아래 참고).

⚠️ **지금은 프로토타입 수준 저장소다** — 프로세스 메모리에만 있어서 서버 재시작하면
전부 사라지고, uvicorn을 여러 워커로 띄우면 워커마다 따로 논다. 실사용 전엔 Redis나
DB 같은 공유 저장소로 바꿔야 한다. 없는 `id`로 조회하면 404.

### `POST /registry/upload` — 등기부 PDF 업로드 (분리 엔드포인트)

`/assessment`와 의도적으로 분리했다. 이유:
1. 무거운 OCR 연산(tesseract/poppler subprocess 호출)을 메인 진단 로직과 격리
2. OCR 오탐지에 대한 사람 확인 버퍼 — 이 엔드포인트는 **진단을 실행하지 않고** 파싱
   미리보기(`registryOcrText`, `owners`, `activeRights`, `totalSeniorSecuredAmount`)만
   반환한다. 유저가 화면에서 텍스트를 확인/수정한 뒤, 그 텍스트를 `/assessment`의
   `registry_ocr_text`에 담아 다시 호출하는 게 다음 단계.

에러 처리: PDF가 아니거나(확장자/`content-type` 둘 다 아님), 15MB 초과, 빈 파일이면 OCR을
아예 돌리지 않고 즉시 400. `find_and_parse_summary_page`가 요약 페이지를 못 찾아
`RuntimeError`를 던지면(서버 버그가 아니라 "이 PDF엔 요약 페이지가 없거나 인식이 안 됐다"는
사용자 입력 문제) 500이 아니라 400으로 변환해서 돌려준다.

## UI 와이어프레임 (2026-09-13, Claude Design 캔버스)

3단계 모바일 유저 플로우 와이어프레임: https://claude.ai/code/artifact/c56fe037-19b4-4277-bd81-3fdf873f1faa

- **Step 1 — 주소·계약조건**: `POST /assessment`의 필수 필드(address, target_area,
  my_deposit, contract_landlord_name, property_type)를 그대로 입력 폼으로 매핑.
- **Step 2 — 서류 확인·자가진단**: 위반건축물 자가진단(필수, 두 옵션 중 하나를 고르기 전엔
  하단 "진단 시작하기" 버튼이 비활성 상태로 보임 — `user_confirmed_violation_building`),
  등기부 PDF 업로드(선택 — `POST /registry/upload` 흐름을 idle → uploading(스피너) →
  uploaded(OCR 텍스트/소유자 이름 편집 가능한 미리보기) 3단계로 시뮬레이션, 실패 시
  화면 상단 토스트 알림 후 idle로 복귀), 완납증명서 제출여부 토글.
- **Step 3 — 진단 결과**: "예시 등급" 칩으로 5개 grade(safe/caution/warning/danger/error)를
  전환하며 신호등 색상·아이콘·판단 근거·세부 카드(매물정보/깡통전세위험/임대인일치/
  사기패턴/완납증명서)가 통째로 바뀌는 걸 확인 가능. 각 카드는 클릭해서 펼치고 접을 수 있음.

**와이어프레임 단계에서 확정된 UX 규칙** (구현 시 그대로 반영할 것):
- 등기부 PDF 업로드는 선택 항목이므로, 업로드 실패(400)나 아예 업로드하지 않은 경우에도
  하단 "진단 시작하기" 버튼은 절대 막지 않는다 — 버튼 비활성화는 위반건축물 자가진단
  (필수 항목) 여부에만 반응한다. `registry_ocr_text`가 비어도 백엔드가 `unknown`으로
  안전하게 처리하는 것과 대응됨.
- PDF 분석은 tesseract/poppler subprocess로 수 초 걸리는 블로킹 작업이므로, idle과
  uploaded 사이에 반드시 별도의 로딩 상태(스피너 + 파일 재선택 버튼 숨김)가 필요하다.

위 와이어프레임은 이제 `frontend/`에 실제 코드로 구현됨 (아래 섹션 참고).

## `frontend/` 실제 구현 (React + Vite + Tailwind CSS v4, 2026-09-13)

와이어프레임의 3단계 흐름을 실제 코드로 옮김. 프레임워크는 React+Vite+Tailwind로 결정
(이유: 이 진단 도구는 입력 후에만 결과가 나오는 구조라 SSR/SEO 이점이 없고, Next.js가
필요해질 랜딩페이지는 나중에 별도 정적 페이지로 붙이는 게 더 간단하다고 판단).

- `src/steps/Step1Address.jsx` / `Step2Documents.jsx` / `Step3Result.jsx` — 와이어프레임
  3화면 그대로 구현. `App.jsx`가 단계 전환과 폼 상태를 관리.
- `src/lib/api.js` — `POST /assessment`, `POST /registry/upload` 실제 fetch 호출
  (`vite.config.js`의 `/api` 프록시가 `http://127.0.0.1:8000`으로 전달).
- **와이어프레임과 실제 구현의 차이 하나**: 와이어프레임엔 등기부 소유자 이름을 별도
  input으로 수정하는 필드가 있었는데, 실제로는 `/assessment`가 `registry_ocr_text` 원문
  하나만 받아서 서버에서 다시 파싱하는 구조라, 소유자 이름 필드만 따로 수정해도 서버에
  반영이 안 되는 이중 소스 문제가 생김. 그래서 구현에서는 OCR 텍스트 textarea 하나만
  편집 가능하게 하고, 소유자/권리 목록은 "최초 인식 결과(참고용)"로 읽기 전용 표시함.
- Step2의 PDF 업로드는 이제 시뮬레이션이 아니라 실제 `POST /registry/upload` 호출 —
  이 개발 환경엔 tesseract/poppler가 없어 실제로 올리면 서버가 500을 내겠지만, 로딩/에러
  토스트 UI 흐름 자체는 정상 작동 확인.
- **실제 백엔드를 처음 띄워서 프론트와 연동하다가 `address_resolver.py`의 진짜 버그를
  발견하고 수정함** (위 "알려진 사실" 섹션 참고). `KAKAO_REST_API_KEY` 없이도 이제
  `overallGrade: "error"`로 깨끗하게 응답하는 것까지 curl로 실제 확인함.
- 이어서 `KAKAO_REST_API_KEY` + `MOLIT_SERVICE_KEY`를 `.env`에 실제로 설정하고 프론트→
  프록시→백엔드 전 구간을 실제 API로 검증 완료 (위 "실제 API 키로 검증 완료" 섹션 참고).
- **카카오(다음) 주소검색 팝업 연동 완료** (2026-09-14) — `src/components/AddressSearchModal.jsx`가
  다음(Daum) 우편번호 서비스 임베드 스크립트(`t1.daumcdn.net/.../postcode.v2.js`)를 동적으로
  로드해 모달로 띄운다. **주의**: 이건 무료 서비스라 API 키가 필요 없고, 백엔드가 쓰는 카카오
  로컬 REST API(주소→PNU 변환)와는 완전히 별개다 — 이 팝업이 된다고 백엔드 카카오 키가
  검증되는 게 아니다(그건 이미 어제 별도로 검증 완료). 주소 선택 후 "상세주소(동/호수)"
  선택 입력 필드가 나타나고, 최종 제출 시 `address` 필드에 합쳐서 보낸다.
- **라우팅(`react-router-dom`) + 세션 지속성 도입 완료** (2026-09-14) — `/step1` →
  `/step2` → `/result/:id` 세 경로로 나눔. 두 계층으로 새로고침/공유에 대응:
  - **Step1/Step2 (입력 폼)**: `src/lib/sessionState.js`가 `form`/`documents` state를
    sessionStorage에 저장 — 같은 브라우저에서 새로고침해도 입력한 값이 안 날아감.
    업로드 중(`uploading`) 상태로 저장돼있으면 복원 시 `idle`로 되돌림(응답 없는 스피너
    방지). 이 폼 데이터는 서버에 저장하지 않는다 — 재현할 이유가 없는 값이라서.
  - **결과 화면**: `POST /assessment`가 반환한 `id`로 `/result/:id`에 진입, 제출 직후엔
    `location.state`로 넘어온 결과를 바로 쓰고(`src/routes/ResultRoute.jsx`), 새로고침
    되거나 링크로 곧장 열리면 `GET /assessment/:id`로 백엔드에서 다시 불러온다 — 다른
    브라우저/기기로 링크를 공유해도 동작(단, 서버 인메모리 저장소라 재시작하면 404).
  - `/step2`를 필수 입력 없이 직접 열면 `/step1`로 리다이렉트하는 가드 있음.
- 아직 없는 것: 배포 설정 (지금은 로컬 `localhost:5173`/`localhost:8000`만 동작) → 아래
  "Docker 배포 스캐폴딩" 섹션에서 뼈대는 잡아둠, 실제 서버에 올리는 건 다음 단계.

## Docker 배포 스캐폴딩 (2026-09-14 작성 → 2026-09-15 정적 검토+인프라 고도화) — ⚠️ 빌드 미검증

로컬에서 완전히 검증된 구조를 컨테이너로 옮기기 위한 뼈대. **이 개발 머신에 Docker 자체가
없어서 실제 `docker compose build`/`up`은 아직 한 번도 못 돌려봤다** — 대신 파일들을
정적으로 검토하면서 실제로 동작을 깨뜨릴 버그 2개를 찾아 고쳤다(아래 참고). 문법과 구성은
표준 패턴을 따랐지만, 처음 빌드할 때 (특히 `pdfplumber` 등 파이썬 패키지의 시스템 의존성)
글루 이슈가 있을 수 있으니 Docker 있는 환경에서 한 번 실제로 빌드해서 검증 필요.

- **`Dockerfile`** (백엔드) — `python:3.13-slim` 기반, `apt-get install tesseract-ocr
  tesseract-ocr-kor poppler-utils`로 OCR 실행파일까지 이미지에 포함. 컨테이너 안에서는
  이 실행파일들이 PATH에 바로 잡히므로 `TESSERACT_CMD` 같은 환경변수는 필요 없음
  (Windows 로컬 개발 환경에서만 필요했던 것과 대비됨 — 위 "Tesseract/Poppler 실환경 검증"
  섹션 참고). `COPY *.py ./`가 `assessment_store.py` 등 새 파일도 자동으로 포함하므로
  이 파일 자체는 안 건드려도 됨.
- **`frontend/Dockerfile`** — Node로 빌드 후 nginx로 정적 서빙하는 2단계 빌드.
  `frontend/nginx.conf`가 `vite.config.js`의 dev 프록시(`/api` → `127.0.0.1:8000`)와
  똑같은 역할을 함(`/api/` → `http://backend:8000/`, 컴포즈 서비스 이름으로 라우팅) +
  `react-router-dom` 클라이언트 라우팅을 위한 `try_files ... /index.html` SPA 폴백.
- **`docker-compose.yml`** — `backend`/`frontend` 두 서비스. **비밀키는 이미지에 절대
  안 굽는다** — `.dockerignore`가 `.env`를 빌드 컨텍스트에서 제외하고, 컴포즈가 `${...}`
  치환으로 필요한 값만 골라서 컨테이너 환경변수로 주입함. 이 방식 덕분에 `.env`에 있는
  Windows 전용 `TESSERACT_CMD` 등의 로컬 경로가 컨테이너 안으로 새어 들어가지 않음
  (어차피 컨테이너 안엔 필요도 없음).
  - 🐛 **2026-09-15 정적 검토로 발견/수정한 버그**: `VWORLD_API_KEY`/`VWORLD_DOMAIN`이
    환경변수 목록에 아예 빠져있었다 — `KAKAO_REST_API_KEY`/`MOLIT_SERVICE_KEY`만 있었음.
    로컬에서 실제로 검증해둔 VWorld 공시가격 연동이, Docker로 배포하면 이 값이 안 넘어가서
    `public_price_adapter.py`가 조용히 항상 "키 없음" 상태(`status: "error"`)로 죽어있는
    채였을 것 — 크래시가 아니라 조용히 죽는 종류의 버그라 실제 배포 전엔 못 알아챘을 위험.
  - 지금은 두 값 모두 추가돼 있음 — 배포 시 `.env`에 `VWORLD_API_KEY`/`VWORLD_DOMAIN`도
    반드시 채워져 있는지 확인할 것(`VWORLD_DOMAIN`은 vworld 키 발급 시 등록한 도메인과
    일치해야 함 — "localhost"로 발급받았다면 운영 도메인으로 재발급 필요할 수 있음).
- **SQLite 볼륨** (2026-09-15 추가): `POST /assessment` 결과 저장소가 인메모리 dict에서
  SQLite(`assessment_store.py`)로 바뀌면서, `docker-compose.yml`에 `./data:/app/data`
  볼륨을 추가했다 — 이게 없으면 컨테이너를 재생성할 때마다(재배포, `down`/`up` 등)
  `/result/:id` 공유 링크가 전부 사라진다. 아래 "다음 단계 후보"의 SQLite 전환 항목 참고.
- 실행 예정 (Docker 설치된 환경에서): `docker compose up --build` → 프론트
  `http://localhost:5173`, 백엔드 `http://localhost:8000`.
- 아직 안 한 것: 실제 빌드 검증(이 항목이 여전히 최우선 — 위 두 버그 수정도 전부 정적
  검토일 뿐 한 번도 실행해서 확인 못 함), 프로덕션 시크릿 관리(지금은 `.env` 그대로 사용),
  여러 워커/여러 서버로 스케일할 때 SQLite → Redis 전환, HTTPS/리버스프록시,
  실제 클라우드/서버 배포 타깃 선정.

### VWorld 배포 서버 검증 체크리스트 (국내 리전 서버가 준비되면 바로 실행)

이 개발 머신은 vworld.kr API 자체 접속이 막혀있어서(싱가포르 등 해외 IP 대역을 vworld가
차단하는 것으로 추정 — 502/커넥션 타임아웃 패턴), 로컬에서는 브라우저로 대신 열어보는
우회로만 검증했다(위 "VWorld 공시가격 연동" 섹션 참고). 실제 배포 서버(서울 리전 등
국내 IP)가 준비되면 이 순서로 확인할 것:

1. **서버 리전 확인** — 클라우드 인스턴스가 국내 리전(예: AWS `ap-northeast-2`)인지 먼저
   확인. 해외 리전이면 이 문제 자체가 재현된다.
2. **`debug_vworld_call.py` 단독 실행** — `.env`에 `VWORLD_API_KEY`/`VWORLD_DOMAIN` 설정
   후 `python debug_vworld_call.py`. 국내 리전인데도 502/타임아웃이면, vworld 마이페이지에
   등록한 "사용 도메인"이 실제 운영 도메인과 다른 게 원인일 가능성이 높음(`domain=localhost`
   로 발급받았다면 재발급 필요).
3. **엔드투엔드 폴백 검증** — 실거래 이력이 없을 법한 매물(신축, 또는 `property_type`이
   `apartment`가 아닌 경우)로 `POST /assessment`를 호출해 `marketPriceConfidence`가
   `"estimated_from_public_price"`로 뒤집히며 VWorld 공시가격 기반 시세가 정상 산출되는지
   확인. `test_full_assessment.py::TestMarketPriceConfidenceWiring`이 이 경로를 모킹으로
   이미 검증해뒀으므로, 여기서는 "진짜 네트워크로도 똑같이 동작하는지"만 확인하면 됨.
4. 위 1~3이 전부 통과하면 이 체크리스트와 "다음 단계 후보"의 관련 항목을 완료 처리할 것.

## VWorld 공시가격 연동 (2026-09-14 준비 → 2026-09-15 검증 완료)

vworld.kr API 서버 자체가 이 개발 머신(싱가포르 IP)에서 계속 불안정(연결 끊김/502,
9/14·9/15 이틀 다 재현)해서, **검증은 전부 지인이 브라우저로 대신 호출해서 받아온
응답으로 진행했다.** 다른 세 어댑터(카카오/실거래가/건축HUB)의 "로직 먼저 → 실키로
검증"과 달리, 검증 자체를 이 머신에서 직접 못 하고 있다는 게 결정적 차이 — 그래도
실제 응답을 확보해서 최종적으로는 똑같이 검증된 상태에 도달함.

**확인된 것 (전부 실제 응답 기반)**:
- `VWORLD_API_KEY`/`domain=localhost` 유효함 (인증 통과)
- **처음 가정했던 엔드포인트가 완전히 틀렸었다** — `req/data`(GetFeature, WFS 계열)가
  아니라 전용 엔드포인트 `GET https://api.vworld.kr/ned/data/getApartHousingPriceAttr`
  였다. vworld 공식 API 레퍼런스 페이지("오픈API → 공동주택가격속성조회")에서 지인이
  캡처해서 확인함.
- **응답이 XML이다** — `format=json`으로 요청해도 상관없이 실제로는 XML이 온다(적어도
  "API결과 미리보기" 버튼 기준). 처음엔 JSON/GeoJSON 스타일로 짰던 게 완전히 틀렸고,
  실제로는 이 프로젝트의 다른 국토부 API 어댑터들과 같은 평범한 XML
  (`<response><fields><field>...<pblntfPc>60000000</pblntfPc>...</field></fields></response>`).
  `public_price_adapter.py`를 XML 파싱(`xml.etree.ElementTree`, 다른 어댑터들과 동일한
  방식)으로 완전히 재작성함.
- **공시가격 필드는 `pblntfPc`, 단위는 원**(샘플 응답 `60000000` = 6천만원) —
  `market_price_estimator.py`가 기대하는 만원 단위로 변환하는 로직 추가함.
- `pnu`만 주고 `dongNm`/`hoNm`을 생략하면 한 단지의 여러 동/호가 `<field>`로 여러 개
  돌아올 수 있다고 보고(실제로 이런지는 미확인), 실거래가와 동일하게 평균 대신
  **중위값**을 쓰도록 설계함(이상치에 덜 흔들리도록).
- 에러 응답 봉투(`status`/`error.code`/`error.text`)는 2026-09-14에 다른 엔드포인트를
  JSON으로 호출해서 확인한 것 — 이 XML 엔드포인트에서 실제로 에러가 XML로 어떻게 오는지는
  아직 실제로 확인 못 함(추정 픽스처 `ASSUMED_ERROR_XML`로만 테스트돼 있음).
- `test_public_price_adapter.py`에 실제 성공 응답(서울 마포구 상암동 상암월드컵1단지
  101동 201호, 공시가격 6천만원)을 `REAL_SUCCESS_XML` 골든 픽스처로 박아둠 — 11개
  테스트 중 성공/빈결과 케이스는 이제 진짜 검증, 에러 케이스만 여전히 추정.

**만들어둔 것**:
- **`public_price_adapter.py`** — `fetch_public_price(pnu)`. 다른 어댑터들과 동일한
  `{"status": "ok"/"not_found"/"error", ...}` 계약. 키 없으면 네트워크 호출 자체를
  안 하고 바로 `invalid_request` 반환(안전한 기본값 — 키가 아직 없던 시점에도
  `property_aggregator.py`에 연결해둔 게 문제 안 됐던 이유).
- **`debug_vworld_call.py`** — 실제 엔드포인트/파라미터로 갱신 완료. 이 머신에서는
  여전히 접속이 막혀서 직접 실행은 안 되지만, 스크립트 자체는 최신 상태.
- **`property_aggregator.py`에 통합 완료** — 실거래가/건축물대장과 병렬 호출,
  `market_price_estimator.estimate_market_price()`의 `public_price` 인자로 흘러들어가서
  실거래가 없을 때 자동 폴백(`confidence: "estimated_from_public_price"`).
  `sourceStatuses.publicPrice`로 성공/실패 항상 투명하게 노출.
- **`vworld_test_link.txt`** (git 추적 제외, 로컬 전용) — 실제 키가 포함된 vworld 테스트
  URL 생성용. 이 머신이 vworld API에 직접 접속이 안 될 때, 링크를 지인 등 한국 IP를
  쓰는 사람에게 보내서 "브라우저에 붙여넣고 결과 캡처해서 보내달라"고 부탁하는 흐름으로
  두 번 다 성공했다 — 자동화 스크립트 요청은 막히는데 브라우저 요청(또는 vworld 자체
  문서 페이지의 "API결과 미리보기" 버튼)은 통과하는 걸 보면 vworld 쪽 보안필터가
  트래픽 종류를 다르게 취급하는 것으로 추정. **이후에도 이 API를 이 머신에서 직접 못
  쓰면 같은 패턴 재사용할 것.**

**남은 할 일**:
1. 에러 응답이 실제로 XML로 어떻게 오는지 확인 (`ASSUMED_ERROR_XML`은 추정) — 급하지
   않음, 에러 시 그냥 `invalid_request`로 떨어지는 동작 자체는 이미 안전하게 보장됨.
2. `dongNm`/`hoNm` 생략 시 정말 여러 `<field>`가 오는지 확인 (중위값 로직이 실제로
   쓰이는 케이스인지, 아니면 거의 항상 1건만 오는지).
3. `api.py`의 `POST /assessment`를 실제로 호출해 `marketPriceConfidence:
   "estimated_from_public_price"`가 나오는 케이스까지 엔드투엔드로 재검증 — 이 머신
   에서는 vworld 직접 호출이 막히므로 배포 서버(국내 리전) 또는 지인 경유로 확인.

## 다음 단계 후보 (우선순위는 상황에 따라 조정)

- [x] `full_assessment.py` 오케스트레이터 작성
- [x] FastAPI 레이어 씌우기 (`api.py`, `POST /assessment` + `GET /health`)
- [x] `POST /registry/upload` 분리 엔드포인트 작성 (PDF 업로드 → OCR 미리보기 전용)
- [x] 화면/UI 와이어프레임 (3단계 흐름, 위 섹션 참고)
- [x] 프론트엔드 프레임워크 선정(React+Vite+Tailwind) + 실제 화면 구현 + 백엔드 실연동 확인
- [x] `KAKAO_REST_API_KEY` + `MOLIT_SERVICE_KEY` 실제 발급/설정 + 전 구간 실제 API 검증
- [x] 카카오(다음) 주소검색 팝업 연동
- [x] `POST /registry/upload`를 실제 tesseract/poppler 환경(Windows, 포터블 설치)에서
      진짜 PDF로 엔드투엔드 재검증 완료 — 위 "Tesseract/Poppler 실환경 검증" 섹션 참고.
      Ubuntu 배포 서버에서는 `apt-get` 설치 후 재확인 권장(기본값으로 바로 동작 예상)
- [x] 라우팅(`react-router-dom`) + 세션스토리지 지속성 + 결과 재조회용 `GET /assessment/{id}`
- [x] Docker 배포 스캐폴딩 작성 (`Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`) —
      **빌드 미검증**, 이 머신에 Docker 없어서 실제로 못 돌려봄. Docker 있는 환경에서
      `docker compose up --build` 한 번 실행해서 검증 필요 (위 섹션 참고)
- [x] VWorld 공시가격 연동 — 정확한 엔드포인트(`ned/data/getApartHousingPriceAttr`) 확인,
      XML 파싱으로 재작성, 실제 성공 응답으로 검증 완료 (2026-09-15, 지인 브라우저 경유) —
      위 "VWorld 공시가격 연동" 섹션 참고. `property_aggregator.py` 통합도 이미 돼 있어
      추가 배선 작업 없이 바로 동작.
- [ ] 이 머신 자체의 vworld API 직접 접속 문제는 미해결 — 배포 서버(국내 리전) 준비되면
      위 "VWorld 배포 서버 검증 체크리스트" 섹션 순서대로 진행할 것.
- [x] 대항력 공백 위험(①) + 확정일자 미확보 위험(②) 룰 엔진 추가 — `tenancy_safety_rules.py`에
      `check_possession_priority_gap_risk`/`check_fixed_date_risk` 신설,
      `registry_summary_parser.py`가 각 권리의 `receivedDate`(접수일)까지 추출하도록 확장,
      `overall_safety_assessment.py`/`full_assessment.py`/`api.py`(`move_in_date`,
      `has_fixed_date` 필드) 전 구간 배선 완료. 날짜 경계값 테스트 다수 포함해 백엔드
      테스트 176→201개, 전부 통과.
- [ ] 최우선변제금(③, 소액임차인 보호) 계산은 의도적으로 보류 — 지역×시점별 정확한 법정
      금액 테이블(여러 차례 개정, 기준일도 계약일이 아니라 등기부상 "가장 오래된 근저당권
      설정일")이 필요한데, 확인 안 된 숫자를 채워넣으면 거짓 안심을 줄 위험이 있음. 검증된
      데이터 출처를 확보하면 재착수.
- [x] 프론트엔드 Step1에 잔금(입주)일 입력 필드, Step2에 확정일자 여부 입력 추가 +
      Step3에 대항력 공백 위험/확정일자 확보 카드 및 타임라인 시각화(`PossessionTimeline.jsx`)
      완료. 백엔드가 `possessionPriorityGapRisk`에 `moveInDate`/`rightsTimeline`(접수일이
      확인된 권리만, 접수일순 정렬)을 함께 내려주도록 확장해서, 새로고침·링크공유로 폼
      상태가 없어도 결과 화면만으로 타임라인을 그릴 수 있게 함(값을 추측해서 채우지 않는
      원칙 유지). 실제 서버(포트 8123)에 curl로 같은 날 접수/다른 날 접수 두 시나리오
      모두 엔드투엔드 검증 완료. 브라우저 실사용 검증 중 확정일자 미확보가 "경고"로
      뜨는 설계 결함 발견 → "caution"으로 하향 완료(아래 최근 업데이트 참고).
- [x] 시세 추정이 property_type을 무시하고 항상 국토부 "아파트매매" 실거래만 비교 대상으로
      쓰던 버그 수정 — 실사용자가 54㎡ 다세대를 진단했는데 근처 아파트 실거래 기준
      14.375억으로 나왔지만(실제 시세는 9~10억) 발견. `연립다세대`/`오피스텔` 전용
      국토부 엔드포인트는 아직 미연동이라, property_type이 "apartment"가 아니면
      `property_aggregator.py`가 아파트 실거래 조회 자체를 건너뛰도록(`sourceStatuses.
      transactionPrice: "skipped"`) 수정하고 공시가격 폴백/unavailable로만 판단하게 함
      — 없는 데이터를 억지로 채우지 않는다는 원칙을 시세 데이터에도 적용. `full_assessment.py`
      가 `property_type`을 `get_property_info`까지 전달하도록 배선(이전엔 전달 자체가
      안 되고 있었음). ⚠️ 남은 과제: 연립다세대/오피스텔 실거래가 API를 실제로 연동하면
      해당 유형도 실거래 기반 "high" confidence를 받을 수 있음 — 지금은 공시가격
      폴백(있으면) 또는 unavailable까지만 나온다. 백엔드 테스트 204→208개 전부 통과,
      실제 서버로 야탑동 335 다세대/아파트 두 property_type 모두 curl 재검증 완료.
- [x] 연립다세대/오피스텔 전용 국토부 실거래가 API 연동 — `real_transaction_price_adapter.py`에
      `fetch_villa_trades`(RTMSDataSvcRHTrade)/`fetch_officetel_trades`(RTMSDataSvcOffiTrade)
      추가, `property_aggregator.py`가 property_type별로 올바른 엔드포인트를 골라 쓰도록
      배선(`_trade_fetch_fn_for()`). ⚠️ 아직 우리 MOLIT_SERVICE_KEY로 직접 검증하지는
      않았다 — 세션 중 태그명 관련 정보가 엇갈려서(한글 태그 주장 vs 영문 태그 주장) GitHub의
      독립 오픈소스 MOLIT 클라이언트(tae0y/real-estate-mcp)를 찾아 대조했고, 정확히 같은
      엔드포인트(Dev 접미사 없음)와 같은 영문 태그(mhouseNm/offiNm/dealAmount/excluUseAr/
      umdNm/cdealType)를 쓰고 있어 지금 구현이 맞을 개연성이 높다고 보고 채택함 — 그래도
      "실제 검증"은 아니므로 실키가 생기면 `debug_villa_officetel_call.py`부터 돌려서
      확인할 것(스크립트 신규 작성 완료). 시세 계산 핵심 필드(dealAmount 등)는 세 API가
      공통이라, 설령 "매물명" 태그가 틀려도 시세 계산 자체는 안 깨지는 구조.
- [x] Docker 배포 인프라 고도화 — (1) `docker-compose.yml`에 `VWORLD_API_KEY`/
      `VWORLD_DOMAIN` 환경변수가 아예 안 넘어가던 버그 발견/수정(로컬에서 검증해둔 VWorld
      연동이 Docker 배포에서는 항상 꺼져있었을 것). (2) `POST /assessment`의 저장소를
      인메모리 dict에서 SQLite(`assessment_store.py`, 표준 라이브러리 sqlite3만 사용, 신규
      의존성 없음)로 전환 — 컨테이너 재시작/재배포마다 `/result/:id` 공유 링크가 전부
      깨지던 문제 해결. `docker-compose.yml`에 `./data:/app/data` 볼륨 마운트 추가로
      영속성 확보, `.gitignore`에 `data/`/`*.db` 추가. Redis는 여러 워커/여러 서버로
      스케일할 때 옮길 다음 단계로 남겨둠(지금은 단일 워커 프로토타입이라 별도 서비스
      운영 부담이 이득보다 큼). ⚠️ 이 머신엔 Docker가 없어 실제 빌드/컨테이너 재시작
      시나리오 자체는 여전히 미검증 — 정적 코드 검토 + SQLite 유닛테스트로만 확인함.
      (villa/officetel 연동 포함) 백엔드 테스트 204→227개 전부 통과.
- [ ] 실제 서버/클라우드에 배포 (배포 타깃 미정) — 배포 시 위 Docker 볼륨/env 변경사항을
      실제로 `docker compose up --build`까지 돌려서 최종 검증할 것.

---
**최근 업데이트**: 2026-09-15 세션 — 세 갈래 작업. ① Docker 배포 정적 검토 중
`docker-compose.yml`에 `VWORLD_API_KEY`/`VWORLD_DOMAIN`이 아예 안 넘어가던 버그(로컬
검증된 VWorld 연동이 Docker 배포에서는 조용히 항상 꺼져있었을 것) 발견/수정, `POST
/assessment` 저장소를 인메모리 dict에서 SQLite(`assessment_store.py`, 신규 의존성 없음)
로 전환해 컨테이너 재배포에도 결과 링크가 살아남게 함 + `docker-compose.yml`에 데이터
볼륨 추가. ② `real_transaction_price_adapter.py`에 연립다세대(RTMSDataSvcRHTrade)/
오피스텔(RTMSDataSvcOffiTrade) 실거래가 API 연동 — 세션 중 태그명 정보가 엇갈려서(한글
태그설 vs 영문 태그설) GitHub의 독립 오픈소스 MOLIT 클라이언트를 찾아 대조 검증하는
과정을 거침(README "연립다세대/오피스텔..." 섹션 참고, 여전히 우리 실키로는 미검증).
③ Step2Documents.jsx의 확정일자 안내 문구를 "계약 전엔 정상 vs 잔금까지 치렀다면 위험"
두 시나리오로 명확히 구분하도록 개선, PossessionTimeline.jsx는 이미 각 이벤트에 "왜
위험한지"(대항력 익일 0시 vs 저당권 당일 즉시) 설명이 붙어있음을 재확인. 날짜 포맷
정합성(프론트 `YYYY-MM-DD` vs 등기부 `receivedDate`)은 `registry_summary_parser.py`가
파싱 시점에 이미 ISO 형식으로 정규화해두므로 별도 변환 없이 안전함을 코드로 재확인.
백엔드 테스트 204→227개 전부 통과, 프론트 lint/build 클린.

---
**이전 업데이트**: 2026-09-14 후속 세션(4) — 시세 추정이 property_type을 완전히 무시하던
버그 수정. 실사용자가 54㎡ 다세대를 진단했는데 "추정 시세 14억 3,750만원"이 나왔지만
실제 시세는 9~10억이라고 보고 → 원인 추적 결과 `real_transaction_price_adapter.py`가
국토부 "아파트매매" 실거래만 조회하는데, `property_aggregator.get_property_info()`가
`property_type`을 아예 받지도 않고 항상 이 데이터를 썼던 게 원인이었다(같은 법정동의
아파트 실거래가가 빌라/다세대 시세로 둔갑). `full_assessment.py`도 `property_type`을
LTV 안전비율에만 쓰고 `get_property_info` 호출에는 전달하지 않고 있었음(둘 다 이번에
고침). 근본 수정: 연립다세대/오피스텔 전용 국토부 엔드포인트가 아직 없으므로,
property_type이 "apartment"가 아니면 아파트 실거래 조회 자체를 건너뛰고(`sourceStatuses.
transactionPrice: "skipped"`) 공시가격 폴백 또는 unavailable로만 판단하도록 함 — 틀린
비교보다 "모른다"가 낫다는 이 프로젝트의 기존 원칙 그대로 적용. 실제 서버로 같은 주소를
apartment/multi_household 두 property_type으로 재조회해 각각 기존 동작 유지/skip 전환을
확인했다. 백엔드 테스트 204→208개 전부 통과. 연립다세대 실거래 API 자체 연동은 별도
후속 과제로 남김(아래 다음 단계 참고).

---
**이전 업데이트**: 2026-09-14 후속 세션(3) — 확정일자 미확보 리스크 등급을 "warning"에서
"caution"으로 하향. 실사용자가 브라우저에서 "확정일자 아직 안 받음"을 선택했더니 "경고"
등급이 뜨는 걸 보고 발견한 설계 결함 — 이 앱은 "계약 전" 진단이 주 사용 시나리오인데,
확정일자(그리고 전입신고)는 계약을 체결해야만 받을 수 있어서 거의 모든 정상 사용자에게
False는 항상 참인 당연한 상태다. "warning"으로 두면 매번 경고가 떠서 실제 위험 신호(대항력
공백, 임대인 불일치 등)의 신뢰도만 깎아먹는다. `check_fixed_date_risk`의 False 분기를
"caution"으로 낮추고 문구도 "계약 전이라면 정상 — 계약 체결 당일 바로 받으세요"로 명확히
함. `overall_safety_assessment.py`도 `identity_risk_level`과 같은 패턴(riskLevel 값을
그대로 escalate)으로 바꿔서 하드코딩된 "warning" 비교를 없앰 — 나중에 다른 호출부가 실제
warning을 넘기는 경우까지 대비. 대항력 공백 룰(①)은 계약 여부와 무관하게 실제 매물 위험이라
그대로 danger 유지. 백엔드 테스트 203→204개, 프론트 lint/build 통과.

---
**이전 업데이트**: 2026-09-14 후속 세션(2) — 대항력 공백 위험/확정일자 미확보 위험 프론트엔드
연동 완료. Step1에 잔금(입주)일, Step2에 확정일자 여부 입력을 추가하고, Step3 결과 화면에
"대항력 공백 위험"/"확정일자 확보 여부" 카드와 `PossessionTimeline.jsx`(잔금일 vs 등기부
접수일 시각 타임라인, 같은 날 충돌이면 빨간 점으로 강조)를 붙임. 타임라인을 새로고침·링크
공유 후에도(폼 상태 없이) 그릴 수 있어야 해서, 백엔드 `check_possession_priority_gap_risk`가
`moveInDate`와 `rightsTimeline`(접수일이 확인된 권리만 접수일순 정렬, 날짜 없는 권리는
추측해서 채우지 않고 제외)을 결과에 항상 함께 내려주도록 확장 — 이 프로젝트의 "확인 안 된
값은 채우지 않는다" 원칙을 프론트 표시 데이터에도 그대로 적용한 것. 포트 8123에 실제 서버를
띄워 잔금일=접수일 동일(danger)/다른 날(safe) 두 시나리오 모두 curl로 엔드투엔드 검증(터미널
cp949 인코딩 때문에 화면 표시는 깨졌지만 JSON 바이트 자체는 UTF-8로 정상임을 python으로
재확인). 브라우저 시각 확인은 아직 안 함. 백엔드 테스트 201→203개, 프론트 lint/build 통과.

---
**이전 업데이트**: 2026-09-14 후속 세션(1) — 대항력 공백 위험(①)/확정일자 미확보 위험(②)
룰 엔진 추가. 임대차보호법상 대항력(전입신고 다음날 0시 발생)과 등기부 권리(접수 당일
즉시 발생)의 타이밍 차이를 이용한 사기 패턴을 잡는 게 핵심 — 잔금(입주)일과 등기부 을구
접수일이 정확히 같은 날이면 danger로 즉시 플래그. `registry_summary_parser.py`가 각
권리의 접수일(`receivedDate`)을 추출하도록 먼저 확장한 뒤, `tenancy_safety_rules.py`에
두 룰을 신설하고 `overall_safety_assessment.py`→`full_assessment.py`→`api.py`
(`move_in_date`/`has_fixed_date` 필드)까지 전 구간 배선. 최우선변제금(③) 계산은 검증
안 된 법정 금액 테이블을 채워넣는 위험 때문에 의도적으로 보류. 날짜 경계값(당일/하루
전/하루 후/정보없음/형식오류) 테스트를 촘촘히 먼저 작성하는 방식으로 진행, 백엔드 테스트
176→201개 전부 통과.

---
**이전 업데이트**: 2026-09-15, VSCode Claude Code 세션 — VWorld 공시가격 연동 완료.
키를 `.env`에 설정하고 검증하는 과정에서 처음 가정했던 엔드포인트(`req/data`
GetFeature, WFS 계열)와 응답 형식(JSON)이 전부 틀렸다는 게 드러남 — 실제로는 전용
엔드포인트(`ned/data/getApartHousingPriceAttr`)에 XML 응답이었다. 이 머신은 vworld
API 접속이 계속 불안정(연결 끊김/502, 이틀 연속 재현)해서 지인이 브라우저(및 vworld
공식 문서 페이지의 "API결과 미리보기" 버튼)로 대신 호출해 받아온 실제 응답으로
`public_price_adapter.py`를 처음부터 다시 작성하고 검증함 — 실제 공시가격(원 단위
`pblntfPc` 필드, 만원으로 변환) 응답까지 확인 완료. `vworld_test_link.txt`(git 미추적)로
"링크 생성 → 브라우저로 대신 열기" 검증 패턴을 두 차례 성공적으로 재사용함. 백엔드
테스트 158→159개, 전부 통과 유지.

2026-09-14 요약: 카카오(다음) 주소검색 팝업 연동, `react-router-dom` 라우팅(`/step1` →
`/step2` → `/result/:id`), Tesseract/Poppler 실환경(Windows) 검증, Docker 배포
스캐폴딩(빌드 미검증), VWorld 공시가격 연동 스텁 준비. 실제 등기부등본 PDF로
`POST /registry/upload` 전 구간 성공, `registry_summary_ocr.py`의 Windows 인코딩
크래시 버그 발견/수정. 백엔드에 `GET /assessment/{id}`를 추가해 결과 화면이
새로고침/링크공유에도 버티게 했고, 프론트 `sessionStorage`로 Step1/Step2 입력 폼도
새로고침에 버티게 함(폼은 세션스토리지만, 결과는 백엔드 재조회까지 — 서로 다른 계층).
백엔드 테스트 146→158개. `CLAUDE.md` 신규 생성, git 저장소 초기화 + 첫 커밋 완료.
전날(2026-09-13) 요약: `full_assessment.py` 오케스트레이터, `api.py`(FastAPI), 3단계 UI
와이어프레임(Claude Design 캔버스), `frontend/`(React+Vite+Tailwind) 실제 구현에 이어
`KAKAO_REST_API_KEY`/`MOLIT_SERVICE_KEY`까지 실제로 설정해 프론트→백엔드→카카오/국토부 API
전 구간을 실제 데이터로 검증 완료 (테스트 118→128→141→146개, 와이어프레임 캔버스 1개).
작업 중 marketPrice 단위 불일치(만원 vs 원) 버그와 `address_resolver.py`의
KAKAO_REST_API_KEY 미설정 시 크래시 버그, 두 개를 실제로 발견/수정. fastapi/uvicorn/httpx/
python-multipart/python-dotenv(백엔드), react/vite/tailwindcss(`frontend/`) 신규 의존성
추가. `.gitignore` 신규 생성(.env, 실제 개인정보 PDF 등 제외 처리).
