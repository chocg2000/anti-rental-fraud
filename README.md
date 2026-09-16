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
2026-09-16 기준 **296개 테스트 전부 통과**.

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
| `registry_gapgu_ocr.py` | 갑구 본문 페이지 전체를 클로바 OCR에 돌려 소유권 이전 이력 추출, `POST /registry/upload`에 배선 | ✅ 실제 PDF+실키로 엔드투엔드 검증 (아래 "클로바 OCR 갑구 파서 라우터 배선" 섹션) |
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

1. ~~공시가격 API 미연결~~ → **2026-09-15 연동 완료, 같은 날 밤 국내 서버로 실검증까지
   완료** (아래 "VWorld 공시가격 연동" / "VWorld 국내 서버 실배포 검증" 섹션 참고).
   이 개발 머신(싱가포르 IP)에서 직접 못 두드리는 문제 자체는 여전하지만, 배포 대상인
   국내 리전 서버에서는 문제없이 동작함을 실제로 확인해서 더 이상 블로커가 아니다.
2. ~~등기부 본문(갑구) 소유권 이전 이력 확보 경로~~ → **2026-09-15 밤 실키 검증 완료**
   (아래 "클로바 OCR 실키 검증" 섹션 참고). `split_line_into_row()`가 아니라 그 앞단
   `reconstruct_lines_from_clova_result()`의 `y_threshold`가 진짜 갭이었다.
3. ~~PDF 업로드 서버에 tesseract/poppler 미설치~~ → **2026-09-14 실환경(Windows) 검증
   완료** (아래 "Tesseract/Poppler 실환경 검증" 섹션 참고). 다만 이건 개발 머신(Windows)
   검증이고, 실제 배포 서버(Ubuntu/Debian 예정)에서는 `sudo apt-get install tesseract-ocr
   tesseract-ocr-kor poppler-utils`로 다시 한번 확인 필요 — PATH 자동 등록되는 환경이라
   `.env`의 `TESSERACT_CMD` 등은 안 넣어도 기본값(`"tesseract"`)으로 바로 동작할 것으로 예상.

## 클로바 OCR 실키 검증 — 소유권보존 갭 해결 (2026-09-15 밤)

지인이 NCP 계정으로 발급해준 클로바 OCR 키(`CLOVA_OCR_INVOKE_URL`/`CLOVA_OCR_SECRET`)로
`debug_clova_ocr_call.py`를 처음으로 실제 실행했다. 대상 이미지는 실사용 등기부(야탑동)가
아니라 `등기부등본_내아파트.pdf` 1페이지(대법원이 제공하는 "테스트용" 워터마크가 찍힌
공식 샘플 — 독도리 토지, 표제부+갑구가 한 페이지에 같이 있는 소량 문서)를 200 DPI로
렌더링해서 썼다 — 클로바의 해상도 상한(가로/세로 8000px)을 넘어 처음엔 `ERROR`가
났었는데, 300→200 DPI로 낮춰서 해결.

- **연결/인증**: `.env`에 처음 넣었던 `CLOVA_OCR_INVOKE_URL`이
  `clovaocr-api-kr.ncloud.com`(사설 IP 10.223.123.60으로 resolve — NCP 내부망 전용
  주소, 공인 인터넷에서 애초에 연결 불가)이었다. 콘솔에서 정식 Invoke URL
  (`https://<도메인>.apigw.ntruss.com/custom/v1/...`)을 다시 확인해서 교체 후 정상
  연결. 변수명도 `.env`엔 `CLOVA_OCR_SECRET_KEY`로 적혀 있었는데 코드는 `CLOVA_OCR_SECRET`을
  읽어서 실제로는 빈 값으로 동작하고 있었음 — 이것도 같이 수정.
- **`reconstruct_lines_from_clova_result()`**: 순수 기하 계산이라 신뢰도 높다던 설계
  그대로, 실제 응답 재조합 결과가 원본 표 순서와 거의 완벽히 일치했다. 다만 순위번호
  "1"(소유권보존)이 본문 줄과는 28px, 그 아래 "(전 1)" 보조줄과는 84px 떨어진 실제
  좌표를 발견 — 이전 기본값 `y_threshold=12`로는 "1"이 양쪽 어디에도 못 붙고 혼자
  떨어져 나와 그 행 전체가 파싱에서 누락됐다. `y_threshold`를 12→30으로 올려서 해결
  (실제 문서의 "본문 줄 ↔ 다음 보조줄" 간격이 최소 84px라 30으로 올려도 서로 다른
  행이 잘못 합쳐질 위험은 없음을 실측으로 확인). `extract_rows_from_clova_result()`가
  이 함수와 별도의 기본값(`12.0`)을 갖고 있던 걸 같이 바꾸는 걸 깜빡했다가 재검증
  과정에서 발견 — 두 함수 모두 30으로 맞춤.
- **`split_line_into_row()`**: 처음 걱정했던 5컬럼 분리 로직 자체는 실제 응답으로도
  문제없이 동작했다(1-1/1-2/1-3 세 행 모두 rank/purpose/receipt/cause/detail이 원본과
  정확히 일치). "⚠️ 미검증" 경고가 걸려 있던 부분인데, 실제로 문제는 그 앞단
  (줄 재조합)에 있었던 것.
- **부작용 1개 발견**: 이 특정 샘플 문서는 표제부와 갑구가 한 페이지에 같이 찍혀 있어서,
  `y_threshold`를 올리니 표제부의 "표시번호"(1, 2, 3...)도 순위번호처럼 보여 노이즈
  행이 같이 뽑힌다. 다만 이 노이즈 행은 `purpose`가 항상 빈 문자열이라
  `registry_parser.parse_gapgu()`가 "소유권보존"/"소유권이전" 키워드 매칭에서 자동으로
  걸러내므로 결과에 영향 없음을 직접 확인했다. 실사용 대상인 아파트 갑구는 보통
  표제부와 별도 페이지라 이 노이즈 자체가 거의 발생하지 않을 것으로 예상.
- 실제 캡처된 좌표를 그대로 재현한 회귀 테스트(`test_rank_number_between_two_wrapped_subrows_joins_content_row`)를 `test_gapgu_ocr_row_parser.py`에 추가. 백엔드 테스트
  287→288개(같은 세션의 VWorld 버그 수정 포함) 전부 통과.
- 남은 것: `POST /registry/upload`(또는 별도 엔드포인트)에 이 클로바 경로를 실제로
  배선하는 작업 — 지금은 `debug_clova_ocr_call.py`로 독립 검증만 끝난 상태.

## 클로바 OCR 갑구 파서 라우터 배선 + 실키 엔드투엔드 검증 (2026-09-16)

위 섹션에서 독립 검증만 끝나 있던 클로바 갑구 OCR을 `POST /registry/upload`에 실제로
연결하고, 실제 등기부 PDF+실제 클로바 키로 라우터 → `parse_gapgu()` → `fraud_pattern_rules.py`
전 구간을 curl 없이 `TestClient`로 직접 검증했다(이 세션의 메인 태스크, 지난 세션이 README에
남긴 계획 그대로).

**갑구 페이지를 사전에 특정하지 않기로 한 설계 결정**: 요약 페이지는 배경무늬가 적어
tesseract로 "주요 등기사항 요약" 마커를 안정적으로 찾을 수 있었지만(`registry_summary_ocr.py`),
갑구 본문은 이 프로젝트가 이미 여러 번 확인한 대로 배경무늬 때문에 tesseract 정확도가 낮다 —
실제로 같은 방식(마커 텍스트 찾기)을 이 PDF의 실제 페이지들에 시험해보니 "갑구" 헤더 자체가
tesseract로 거의 안 잡히는 페이지가 있었다(반면 "을구" 헤더는 부분적으로 잡힘 — 안정적인
판별 기준으로 쓰기엔 불충분). 그래서 `registry_gapgu_ocr.py`는 페이지를 사전에 고르지
않고 요약 페이지를 제외한 모든 페이지를 순서대로 클로바 OCR에 보낸 뒤, `parse_gapgu()`가
"소유권보존"/"소유권이전" 키워드가 없는 행(표제부, 을구 등)을 알아서 걸러내게 한다 —
등기부 PDF가 보통 5~15페이지라 페이지 수만큼 클로바 호출이 늘어나는 비용은 새 판별 로직을
만드는 것보다 감당 가능한 트레이드오프라고 판단했다. 클로바 키가 없으면(로컬 개발 등)
다른 어댑터들과 같은 패턴으로 아예 호출하지 않고 빈 결과를 반환하고, 개별 페이지 렌더링/
호출이 실패해도 그 페이지만 건너뛴다(부분 실패 허용).

**리팩터링**: `registry_summary_ocr.py`의 PDF 페이지 카운트/렌더링 로직(`_pdf_page_count`,
페이지→PNG 렌더링)을 `pdf_page_count()`/`render_pdf_page_to_png_bytes()`로 공개 함수화해서
`registry_gapgu_ocr.py`가 그대로 재사용하게 했다 — TESSERACT_CMD/PDFTOPPM_CMD 등 실행파일
경로 관리가 한 곳에만 있어야 하기 때문. 요약 페이지 OCR 흐름 자체의 동작은 바뀌지 않았음을
아래 실제 PDF 엔드투엔드 검증으로 재확인했다(9페이지짜리 실제 PDF에서 여전히 9번째 페이지를
정확히 찾음).

**실제 PDF(`등기부등본_내아파트.pdf`, 총 9페이지 — 대법원 공식 샘플(독도리 토지, 1~2페이지)와
실제 야탑동 아파트 등기부(3~9페이지)가 이어붙어 있는 로컬 전용 테스트 파일)+실제 클로바 키로
`POST /registry/upload`를 `TestClient`로 직접 호출**해 확인:
- 요약 페이지(9번째) 자동 탐지 그대로 유지, 갑구 OCR은 나머지 8페이지 전부 처리(실패 0건).
- `ownershipHistory`에 실제 소유권 이전 이력 5건이 정확한 날짜·이름으로 추출됨: 1968-03-13
  국(위 샘플 문서의 소유권보존, 노이즈지만 무해함) → 1999-02-10 이윤재 → 2003-07-21 김수자 →
  2005-03-04 김하기 → 2015-07-17 조춘근(최종 현재 소유자, 요약 페이지의 "조춘근"과 정확히
  일치). 표제부(1~4페이지에 섞여 있음)와 을구(6~8페이지) 행이 같은 배치에 섞여 들어가도
  `parse_gapgu()`가 정확히 걸러내 결과를 오염시키지 않음을 실제 데이터로 확인.
- **실제 버그 발견/수정**: 처음 실행했을 땐 최종 소유자(2015-07-17 조춘근)가 통째로 빠졌다.
  원인은 등기목적 칸이 좁아 "공유자전원지분전부이전"이 문서 원본에서 "공유자전원지분전부"/
  "이전" 두 줄로 나뉘어 인쇄돼 있었고, "이전"만 있는 둘째 줄은 순위번호가 없어
  `gapgu_ocr_row_parser`의 행 재조합 단계에서 노이즈로 걸러졌기 때문 — 그 결과 실제
  `purpose` 값이 "공유자전원지분전부"까지만 남아 `parse_gapgu()`의 "소유권이전" 문자열
  매칭에 안 걸렸다. `registry_parser.parse_gapgu()`의 매칭 조건에 "지분전부"를 추가해서
  해결(회귀 테스트를 실제 캡처된 값 그대로 `test_registry_parser.py`에 추가). 이 프로젝트가
  실제 데이터로 검증할 때마다 반복적으로 겪어온 패턴(문서/가정과 실제 응답이 미묘하게
  다름)이 여기서도 그대로 재현됨.
- `fraud_pattern_rules.detect_new_villa_recent_ownership_change()`를 이 실제 이력으로
  직접 호출해 신축+최근 소유권 변경 조합(트리거)과 비신축(미트리거) 두 케이스 모두 의도대로
  동작함을 확인. `full_assessment.run_full_assessment()`에 이 이력을 그대로 흘려보내고,
  `POST /assessment`를 `TestClient`로 호출해 Pydantic 직렬화까지 포함한 전 구간에서
  `fraudPatternResult.triggered=true`, `overallGrade="warning"`이 정확히 나오는 것까지
  확인 — README "🎯 다음 세션 메인 태스크"가 요구했던 엔드투엔드 검증 완료.
- **프론트엔드도 최소 배선**: `Step2Documents.jsx`가 `registryPreview`에 `ownershipHistory`를
  저장하고 화면에 참고용 칩으로 표시하며, `App.jsx`의 `buildPayload()`가 값이 있으면
  `/assessment`의 `ownership_history`로 그대로 전달하도록 추가함 — 이전까지는 백엔드가
  이 필드를 이미 받을 수 있었는데도 프론트에서 채워 보내는 경로 자체가 없었다.
- (부수 수정) `run_all_tests.py`의 마지막 요약 출력이 em dash(—) 때문에 Windows
  콘솔(cp949)에서 `UnicodeEncodeError`로 크래시하던 걸 발견 — 전체 테스트가 통과했는데도
  이 print 크래시 때문에 스크립트가 비정상 종료(exit code 1)하고 있었다. 하이픈으로 교체.
- 신규: `registry_gapgu_ocr.py` + `test_registry_gapgu_ocr.py`(6개, 페이지 오케스트레이션만
  모킹 검증 — 줄 재조합/컬럼분리/갑구판별 로직은 각자의 기존 테스트가 커버). 백엔드 테스트
  288→296개 전부 통과. 프론트 lint/build 클린.
- ⚠️ 남은 과제: 을구 치명적 키워드(임차권등기명령 등)나 을구 근저당권 채권최고액 합계를
  이 클로바 경로로 자동 추출하는 건 이번 스코프 밖(API의 `registry_critical_keywords`
  필드는 여전히 프론트/자동화 어느 쪽에서도 채워지지 않음 — 을구 쪽은 요약 페이지의
  전세권/근저당 합계로 이미 커버되고 있어 우선순위가 낮다고 판단). 등기부 PDF가 아주
  길면(예: 소유권 이전이 잦은 오래된 건물) 페이지 수만큼 클로바 호출 비용이 커지는 점도
  아직 실사용 트래픽으로 검증 못함.

## 네이버 클로바 OCR 연동 설계 (2026-09-15) — ✅ 실키 검증 완료 (위 섹션 참고)

등기부 본문(갑구/을구) 페이지는 위변조 방지 배경무늬 때문에 Tesseract 정확도가 낮고,
스캔 이미지라 pdfplumber도 텍스트를 못 뽑는다. 그래서 이 본문만 상용 OCR(네이버 클로바
General, V2)로 대체하는 경로를 새로 열었다. **핵심은 여기서 새 판별 로직을 만들지
않는다는 것** — `registry_parser.py`의 `parse_gapgu()`/`parse_eulgu()`는 이미 완성돼
있고 테스트 12개가 통과한 상태였다(rank/purpose/receipt/cause/detail 딕셔너리 리스트를
입력으로 받음). 진짜 빠져있던 건 "스캔 이미지에서 그 딕셔너리를 어떻게 뽑아내는가" 하나뿐.

- **`clova_ocr_adapter.py`** — 클로바 General OCR(V2) 호출 어댑터. 요청 스펙(Invoke URL
  형식, `X-OCR-SECRET` 헤더, `images[].format/name/data`, `version="V2"`)은
  [네이버 공식 문서](https://api.ncloud-docs.com/docs/ai-application-service-ocr-ocr)로
  확인. 키가 없으면 `public_price_adapter.py`와 같은 패턴으로 네트워크 호출 자체를
  안 하고 안전하게 `error`를 반환한다.
- **`gapgu_ocr_row_parser.py`** — 두 단계로 나뉜다:
  1. `reconstruct_lines_from_clova_result()` — 클로바가 돌려주는 개별 텍스트 조각
     (`inferText` + `boundingPoly.vertices`)을 y좌표로 그룹핑(스캔 기울어짐 허용
     오차 있음) 후 x좌표로 정렬해 위→아래 순서의 텍스트 줄로 재조합한다. 순수 기하
     계산이라 신뢰도 높음 — 실제 키 없이도 완전히 검증됨.
  2. `split_line_into_row()` — 재조합된 한 줄을 rank/purpose/receipt/cause/detail
     5개 컬럼으로 나눈다. ⚠️ 이 부분이 진짜 미검증 지점 — 실제 클로바 OCR 결과를 한 번도
     못 봤고, 등기부 본문의 실제 줄바꿈/공백 패턴을 가정해서 짰다. 다만 최악의 경우
     결과가 "판별 불가"(거짓 음성)로 떨어질 뿐, 시세·법정 금액 같은 "거짓 안심"류
     위험은 없다 — `fraud_pattern_rules.py`가 이력 데이터 부재를 이미 명확히 구분해서
     처리하기 때문.
  구현 중 회귀 테스트로 실제 버그 하나를 잡았다: "말소" 기록("3번가압류등기말소")의
  등기목적을 어휘 매칭으로 "가압류"만 뽑으면 "말소" 텍스트가 잘려나가
  `registry_parser._CANCEL_REF_PATTERN`의 취소 판별이 깨졌다 — 말소 패턴을 어휘
  매칭보다 먼저 확인하도록 수정.
- **`debug_clova_ocr_call.py`** — 실제 Secret Key가 생기면 가장 먼저 돌려볼 스크립트.
  실제 등기부 갑구 이미지를 넣으면 원본 응답, 재조합된 줄, 컬럼 분리 결과까지 한 번에
  출력한다.
- 실제 검증 순서(실키 확보 후): ① `debug_clova_ocr_call.py`로 원본 응답 구조 확인 →
  ② `reconstruct_lines_from_clova_result()`의 `y_threshold` 값이 실제 해상도에
  맞는지 확인 → ③ `split_line_into_row()`가 실제 갑구 레이아웃과 맞는지 확인, 안 맞으면
  이 함수만 다시 짜면 됨(뒷단 `parse_gapgu()`는 안 건드려도 됨) → ④ `POST
  /registry/upload`(또는 별도 엔드포인트)에 실제로 배선.
- 백엔드 테스트 266→286개 전부 통과(클로바 어댑터 6개 + 행 파서 14개, 전부 모킹/합성
  fixture 기반 — 실제 응답 검증 아님).

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

## Docker 배포 스캐폴딩 (2026-09-14 작성 → 09-15 정적 검토+인프라 고도화 → 09-15 실빌드 검증 완료) — ✅

**2026-09-15 저녁, 이 개발 머신(Windows 11 Home)에 Docker Desktop을 설치해 실제로
`docker compose build`/`up`까지 전부 돌려서 검증 완료.** 아래는 그 결과:

- `docker compose build` — 백엔드/프론트엔드 이미지 둘 다 빌드 성공. `python:3.13-slim`
  위에서 `pdfplumber`(cryptography/cffi 등 네이티브 의존성 포함)와
  `apt-get install tesseract-ocr tesseract-ocr-kor poppler-utils`가 전부 문제없이
  설치됨 — 이게 이 섹션에서 가장 걱정했던 지점이었는데 실제로는 깔끔했다.
- `docker compose up -d` — 두 컨테이너 정상 기동. 프론트(nginx)가 `/api/`를
  `http://backend:8000/`으로 정확히 프록시(컴포즈 내부 DNS로 서비스 이름 해석 확인).
- 실제 카카오/국토부 키로 `POST /assessment` 엔드투엔드 성공(`transactionPrice: "ok"`,
  `buildingRegister: "ok"`) — VWorld만 이 머신 특유의 IP 차단으로 여전히 `error`
  (예상된 결과, 아래 "VWorld 배포 서버 검증 체크리스트" 참고).
- **SQLite 볼륨 마운트 실검증** — `./data/assessments.db`가 호스트에 실제로 생성됨을
  확인. 결정적으로, `docker compose down && docker compose up -d`(컨테이너 완전
  재생성, 단순 재시작이 아님)를 실행한 뒤에도 `GET /assessment/{id}`로 이전 결과가
  그대로 조회됨 — 오늘 낮에 고친 `ASSESSMENT_DB_PATH` 명시 고정(커밋 `6afb4f2`)이
  실제로 의도대로 동작함을 실환경에서 확인.
- `docker exec`로 컨테이너 안에서 `tesseract --version`(5.5.0, `kor` 언어팩 포함)과
  `pdftoppm -v`(poppler 25.03.0) 직접 실행 확인 — `POST /registry/upload`가 실제로
  쓸 실행파일들이 정상 동작.

이걸로 이 프로젝트의 "로컬에서만 검증된 상태"의 마지막 큰 리스크(Docker 빌드)가 해소됐다.
남은 건 VWorld(국내 리전 서버 필요)와 클로바 OCR(NCP 키 필요) 둘뿐 — 아래 "🎯 지금
최우선" 섹션 참고.

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

### VWorld 배포 서버 검증 체크리스트 — ✅ 2026-09-15 밤 전부 완료

이 개발 머신은 vworld.kr API 자체 접속이 막혀있어서(싱가포르 등 해외 IP 대역을 vworld가
차단하는 것으로 추정 — 502/커넥션 타임아웃 패턴), 로컬에서는 브라우저로 대신 열어보는
우회로만 검증했었다(위 "VWorld 공시가격 연동" 섹션). 아래 1~4를 지인이 제공한 국내
리전 서버(211.233.216.8, NCP)에서 전부 실행해 완료했다 — 자세한 경위는 바로 아래
"VWorld 국내 서버 실배포 검증" 섹션 참고.

1. [x] **서버 리전 확인** — NCP 국내 리전 서버, Ubuntu 24.04.1 LTS.
2. [x] **`debug_vworld_call.py` 단독 실행** — 컨테이너 안에서 실행, `status_code: 200`
   + 실제 데이터(서울 마포구 상암동) 수신 확인. 이 머신에서 겪던 502/타임아웃이 국내
   리전에서는 전혀 재현되지 않음.
3. [x] **엔드투엔드 폴백 검증** — `POST /assessment`로 다세대주택 매물을 조회하는 과정에서
   `public_price_adapter.py`의 실제 버그(결과 0건일 때 `<fields>` 태그 생략을 파싱
   에러로 오분류)를 발견/수정함 — 아래 섹션 참고. 이 매물 자체는 마침 실거래 데이터가
   있어 `"estimated_from_public_price"` 폴백 케이스까지는 못 봤지만, `not_found` 정상
   분류와 `market_price_estimator`의 폴백 로직 자체는 기존 유닛테스트
   (`test_full_assessment.py::TestMarketPriceConfidenceWiring`)로 이미 검증돼 있어
   조합 리스크는 낮다고 판단.
4. [x] 완료 처리.

## VWorld 국내 서버 실배포 검증 (2026-09-15 밤)

지인이 제공한 NCP(네이버클라우드플랫폼) 국내 리전 서버(`211.233.216.8`, Ubuntu 24.04.1
LTS, `yongtiger.pem` 키)에 `deploy.bat`로 실제 배포하고, 컨테이너 안에서 vworld를
직접 두드려 이 프로젝트의 마지막 외부 리소스 블로커를 해소했다.

**배포 과정에서 겪은 문제들 (전부 실제로 발견/해결)**:
- `deploy.bat`이 원래 AWS 스타일(`ubuntu` 계정, `usermod`로 docker 그룹 추가)로 짜여
  있었는데, **NCP Ubuntu 서버는 기본 계정이 `ubuntu`가 아니라 `root`**였다 —
  `ubuntu@`/`root@` 둘 다 pubkey 인증이 거부돼서 원인을 좁혀가다 확인.
- **NCP는 키 페어를 AWS처럼 SSH pubkey로 바로 쓰지 않는다** — 키는 콘솔의 "관리자
  비밀번호 확인" 기능으로 초기 랜덤 비밀번호를 복호화하는 용도였다. 그 비밀번호로 먼저
  1회 로그인해서 `yongtiger.pem`의 공개키를 `/root/.ssh/authorized_keys`에 수동
  등록한 뒤에야 키 기반 SSH가 정상 동작했다. (비밀번호는 대화창에 남기지 않고 사용자가
  직접 터미널에서 처리 — 키 등록 후 `PasswordAuthentication no`로 비밀번호 로그인
  자체를 비활성화해서 무차별 대입 공격 표면을 없앰. `/etc/ssh/sshd_config.d/
  50-cloud-init.conf`가 메인 `sshd_config`보다 먼저 적용되는 override라는 것도 여기서
  확인 — Ubuntu cloud-init 이미지는 이 드롭인 파일을 고쳐야 실제로 반영된다.)
- `deploy.bat`이 `frontend/index.html`을 scp 목록에서 빠뜨려서 Vite 빌드가 실패할
  뻔했다 — Vite는 프로젝트 루트에 `index.html`이 반드시 있어야 진입점을 찾는다.
- `docker-compose.yml`이 `.env`에 `VWORLD_DOMAIN`이 없으면 컨테이너에 **빈 문자열을**
  주입한다는 걸 재확인 — `public_price_adapter.py`의 기본값 로직(`os.environ.get(...,
  "localhost")`)은 변수가 아예 없을 때만 동작하지, 빈 문자열이면 그대로 써버린다.
  `.env`에 `VWORLD_DOMAIN=localhost`를 명시해서 방지.
- **우분투 apt 기본 `docker-compose`(v1.29.2, 레거시 파이썬 구현)가 이미지 재빌드 후
  컨테이너 재생성 시 `KeyError: 'ContainerConfig'`로 깨지는 걸 발견** — 최근 Docker
  빌드가 만드는 이미지 메타데이터 포맷과 legacy docker-compose가 안 맞는 알려진
  호환성 문제. 해결: 깨진 컨테이너를 `docker rm -f`로 지우고 `docker-compose up -d`를
  다시 실행하면 정상 생성된다(재생성 경로를 피하고 새로 만드는 경로를 타게 됨). **앞으로
  이 서버에 재배포할 때마다 재현될 수 있으니, `docker-compose up --build -d`가 이
  에러를 내면 이 순서로 대응할 것** — 근본적으로는 `docker-compose-plugin`(v2, `docker
  compose` 명령)으로 갈아타는 게 정석이지만 지금은 우회로 충분.

**실제 검증 결과**:
- `debug_vworld_call.py`를 컨테이너 안에서 실행 → `status_code: 200`, 실제 공시가격
  데이터(서울 마포구 상암동 상암월드컵1단지) 정상 수신.
- `POST /assessment`로 실제 주소(성남시 분당구 야탑동 335, 다세대주택으로 조회) 호출 →
  `public_price_adapter.fetch_public_price()`가 `{"status": "error", "reason":
  "invalid_request"}`를 반환하는 걸 발견 — 원본 XML을 직접 찍어보니
  `<response><totalCount>0</totalCount></response>`처럼 **결과 0건일 때 `<fields>`
  태그 자체가 생략**되는데, 코드가 이를 "예상 밖 구조"로 보고 에러 처리하고 있었다.
  `totalCount`가 명시적으로 `"0"`이면 정상적인 `{"status": "not_found"}`로 처리하도록
  수정, 실제 응답을 골든 픽스처(`REAL_NO_RESULT_XML_NO_FIELDS_TAG`)로 고정.
- 수정 후 같은 요청으로 `{"status": "not_found"}` 정상 반환 확인. 백엔드 테스트
  287→288개 전부 통과(로컬), 수정한 파일을 서버에 재전송 후 이미지 재빌드까지 마침.

**다음에 이어서 할 것**: `.env`의 `TESSERACT_CMD`/`PDFTOPPM_CMD`/`PDFINFO_CMD`는
Windows 전용 값이라 이 서버(컨테이너 안엔 apt-get 설치본이 PATH에 있음)엔 원래
필요 없지만 `.env`를 통째로 scp해서 같이 넘어갔다 — 컨테이너 환경변수로는 안 들어가서
(docker-compose.yml이 특정 키만 주입) 무해하지만, 신경 쓰이면 서버용 `.env`를 별도로
만들어 관리하는 것도 고려할 만함. `POST /registry/upload`에 클로바 OCR 갑구 경로를
아직 안 붙인 것도 남은 작업(위 "클로바 OCR 실키 검증" 섹션 참고).

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

### ✅ 클로바 OCR 갑구 파서를 실제 라우터에 배선 — 2026-09-16 완료

독립 검증(위 "클로바 OCR 실키 검증" 섹션)이 끝난 클로바 OCR 경로를 `POST /registry/upload`에
정식 연결하고, 실제 PDF+실키로 `parse_gapgu()` → `fraud_pattern_rules.py` → `/assessment`
전 구간까지 엔드투엔드 검증 완료. 자세한 내용은 위 "클로바 OCR 갑구 파서 라우터 배선 +
실키 엔드투엔드 검증" 섹션 참고. 진행 중 실제 데이터로 새 버그(등기목적 줄바꿈으로 최종
소유자가 누락되던 문제)를 발견해 `registry_parser.parse_gapgu()`를 수정했고,
`Step2Documents.jsx`/`App.jsx`에 최소한의 프론트 배선(미리보기 표시 + `/assessment`
전달)도 같이 끝냈다.

### 🎯 다음 세션 후보 태스크

1. ~~을구 자동 데이터 추출은 아직 없음~~ → **2026-09-16 로직 실키 검증 + 라우터 배선
   전부 완료.** 아래 "을구 파이프라인 배선 + 행 파서 재설계" 섹션 참고.
2. ~~실사용 트래픽 기준 클로바 호출 비용/속도 미검증~~ → **2026-09-16 실측 완료, 심각한
   지연 확인됨.** `등기부등본_내아파트.pdf`(9페이지, 요약 제외 8페이지)를
   `extract_ownership_history_from_pdf()`로 직접 돌려본 결과 **239초(약 4분)** 걸렸다
   — 페이지마다 순차적으로 클로바를 호출하고(각 호출 타임아웃 20초, `clova_ocr_adapter.py`),
   렌더링(`pdftoppm`)까지 더해지기 때문. B2C는 `USE_CLOVA_OCR=false`라 이 경로 자체를
   안 타서 영향 없지만, **B2B로 이 기능을 켜는 순간 페이지 수가 많은 등기부(10~15페이지)는
   유저가 몇 분씩 대기해야 하는 UX 문제가 된다.** B2B 착수 시 우선 검토할 것:
   (a) 클로바 호출을 페이지별 순차가 아니라 병렬(스레드풀/asyncio)로 바꿔서 8페이지
   기준 4분 → 십수 초로 단축, (b) `POST /registry/upload`에 실제 소요시간에 맞는
   타임아웃/진행률 UI 필요(현재 프론트 `uploadRegistryPdf()`는 fetch 타임아웃이 아예
   없어 무한정 기다림 — Step2Documents.jsx의 "보통 몇 초 걸려요" 문구도 B2B에서는
   완전히 틀린 문구가 됨, B2C 기본값에서는 클로바를 안 타므로 여전히 맞는 문구).
3. ~~브라우저 실사용 검증~~ → **2026-09-16 부분 완료.** Step2 업로드 → 갑구 이력 칩
   렌더링까지는 실제 브라우저로 확인 완료(위 클로바 실측 항목 참고, owner 5건 —
   국/이윤재/김수자/김하기/조춘근 — 모두 정확히 파싱됨). 다만 Step3Result.jsx의
   새 "사기 패턴 탐지" 헤드라인 배너/`OwnershipTimeline`은 아직 화면으로 못 봤다 —
   테스트에 쓴 `등기부등본_내아파트.pdf`가 1993년 준공 건물이라 "신축빌라(사용승인
   1년 이내)" 조건 자체를 못 채워 `fraud.triggered`가 항상 false로 나오기 때문.
   실제 신축 건물의 등기부(또는 그런 조건을 만족하는 합성 데이터)로 다시 확인 필요.

### ✅ 을구 실키 검증 — 행 파서 버그 3개 발견/수정 (2026-09-16 밤)

`registry_parser.parse_eulgu()`와 `gapgu_ocr_row_parser.py`의 행 재구성/컬럼분리
로직은 "이미 완성"으로 표시돼 있었지만, 실제로는 **을구 실데이터로 한 번도 검증된
적이 없었다**(갑구만 실키 검증됨). `등기부등본_내아파트.pdf`의 을구 페이지(6~8)를
클로바로 직접 돌려서(`debug_eulgu_ocr_call.py`) 검증한 결과 **말소된 근저당권
151,200,000원을 여전히 유효한 것으로 잘못 합산**하는 실제 버그를 발견 — 정답은
0원(이 문서의 을구는 근저당권이 전부 말소된 상태, 현재 유효한 건 전세권 3억원뿐이고
이건 요약 페이지가 이미 커버함). 원인을 파고들며 서로 다른 버그 3개를 발견/수정했다:

1. **말소 등기목적이 물리적으로 여러 줄에 걸쳐 찍히는 경우 병합 안 됨.**
   "1번근저당권설정, 2번근저당권설정등기말소"처럼 칸이 좁아 실제로는 3줄로 찢어져
   나오는데, 줄마다 따로 `split_line_into_row()`를 호출해서 "등기말소"가 적힌 뒷줄이
   통째로 버려지고 있었다 — `gapgu_ocr_row_parser._group_lines_into_row_blocks()`를
   추가해 순위번호로 시작하는 줄을 기준으로 다음 순위번호 줄이 나오기 전까지 전부
   합치도록 고침.
2. **한 줄이 순위번호 2개를 한꺼번에 말소하면 첫 번째만 인식됨.** "1번근저당권설정,
   2번근저당권설정등기말소" 자체도, 정규식(`_CANCEL_REF_PATTERN`)이 "1번"만 캡처하고
   greedy 매칭 때문에 "2번"을 놓치는 별도 버그가 있었다 — `registry_parser._find_canceled_ranks()`가
   "말소" 키워드 앞부분 전체에서 순위번호를 다 훑도록 고침.
3. **행 재조합의 y좌표 그룹핑이 "고정 anchor" 방식이라 특정 조각이 통째로 이탈.**
   `reconstruct_lines_from_clova_result()`가 "그 행에서 가장 먼저 들어온 조각 하나"를
   anchor로 고정하고 나머지를 그것과만 비교했는데, 한 행 안에서도 컬럼마다(순위번호/
   등기목적/상세) 텍스트 기준선이 미세하게 어긋나다 보니 anchor가 하필 반대쪽 끝
   컬럼이면 실제 행 높이만큼 거리가 벌어진다. 실제로 순위번호 "5"(채권최고액
   138,000,000원짜리 근저당권설정 행)가 anchor와 33px 차이로 30px 임계값을 근소하게
   넘겨 완전히 다른 행으로 떨어져 나갔다 — 이 행 전체가 통째로 유실될 뻔했다(우연히
   4번 근저당권과 같은 그룹으로 잘못 합쳐지면서 4번이 말소 대상이라 결과적으로는
   맞게 나왔지만, 순전히 우연이었다). "연쇄 간격" 클러스터링(직전 조각과의 거리만
   비교, anchor 고정 안 함)으로 바꿔서 근본적으로 해결.
4. **(버그는 아니지만 위험한 시나리오) 페이지 하단 법적 고지문이 마지막 행에 섞여
   들어갈 뻔함.** 대법원 인터넷등기소가 모든 페이지에 찍는 "실선으로 그어진 부분은
   말소사항을 표시함"이라는 고지문 자체에 "말소"가 들어있고, 그 앞줄 "11번 등기는
   건물만에 관한 것임"에는 "11번"이 들어있다 — 이 둘이 마지막 데이터 행에 그대로
   병합되면 **실제로는 유효한 11번 전세권(3억원)이 말소된 것으로 잘못 판정**될 뻔했다.
   `_FOOTER_NOISE_MARKERS` 블랙리스트를 추가해 이런 고지문/발급정보/페이지번호
   (`N/M` 패턴)를 행에 편입되기 전에 걸러내도록 방어.

재검증 결과 `parse_eulgu()`가 정확히 `{"criticalKeywords": [], "seniorMortgageAmount": 0,
"estimatedActualDebt": 0, "jointCollateralDetected": false}`를 반환 — 사람이 읽은
결과와 일치. 회귀 테스트 4개 추가(`test_gapgu_ocr_row_parser.py`/`test_registry_parser.py`),
백엔드 전체 302개 테스트 통과. `debug_eulgu_ocr_call.py`는 다음 실키 검증에 재사용
하도록 남겨뒀다(패턴: `run_real_*.py`/`debug_*.py`).

이 세션 시점에는 이 결과를 실제 파이프라인에 배선하지 않고 여기서 멈췄다 — 행 파서
자체의 신뢰도를 먼저 확보한 뒤 배선해야 나중에 "파서 문제"와 "스코어링 로직 문제"가
뒤섞이지 않는다는 판단. **배선 자체는 바로 다음 세션(같은 날 밤)에 진행했고, 그 과정에서
행 파서에 남아있던 진짜 회귀 버그를 하나 더 발견했다 — 아래 "을구 파이프라인 배선 +
행 파서 재설계" 섹션 참고.**

**금액 표기 관련 남은 제약**: `_AMOUNT_PATTERN`은 "채권최고액 금115,200,000원"처럼
아라비아 숫자 표기만 인식한다. 이 문서의 1993~1995년산 근저당권 2건은 "금일천오백육십만원정"
(한글 숫자 표기)이라 애초에 금액 자체를 못 뽑는다 — 다만 이 두 건 모두 결국 말소
대상이라 최종 결과에는 영향 없었다. **2026-09-16 밤 후속 조치**: 한글 숫자 파서를
새로 만들지는 않았지만(실제 서비스에서 아직 유효한 근저당이 이 표기를 쓰는 빈도를
알 수 없어 굳이 만들 근거가 부족함), 대신 "말소 안 된 근저당인데 금액을 못 읽었다"는
사실 자체를 숨기지 않도록 `hasUnparsedMortgageAmount` 신호를 추가해 caution으로
반영했다 — 아래 "을구 한글 숫자 금액표기 — 파서 대신 정직한 신호로 대응" 섹션 참고.

### ✅ 을구 파이프라인 배선 + 행 파서 재설계 (2026-09-16 밤, 같은 날 이어서)

위 "을구 실키 검증" 섹션에서 미뤄뒀던 배선을 진행했다: `registry_gapgu_ocr.py`가
`parse_eulgu()` 결과도 함께 반환하도록 확장하고, `POST /registry/upload` 응답에
`eulguValidSecuredAmount`/`hasRentRightCommand` 필드를 추가, `full_assessment.py`에
`eulgu_valid_secured_amount` 파라미터를 추가해 요약 페이지 합계와 **교차검증 후 더 큰
쪽을 채택**(Max Fallback — OCR이 근저당을 놓쳐도 위험을 과소평가하지 않기 위함)하도록
했다. 임차권등기명령은 새 판정 로직을 만들지 않고 기존 `registry_critical_keywords`
최우선 규칙(있으면 즉시 danger)에 그대로 합류시켰다 — `api.py`가 `has_rent_right_command`를
받아 그 리스트에 합쳐 넣기만 한다. 프론트(`Step2Documents.jsx`/`App.jsx`)도 같은
패턴으로 배선.

**배선 검증 중 실제로 심각한 회귀 버그를 발견했다.** 실키로 전체 파이프라인을
엔드투엔드 재검증(`extract_ownership_history_from_pdf`를 실제 API 엔드포인트 경로
그대로 호출)했더니 `ownershipHistory`가 갑자기 빈 배열로 나왔다 — 바로 위 섹션에서
분명히 검증됐던 기능이었다. 추적 결과, 원인은 **을구 버그를 고치려고 추가했던
`_group_lines_into_row_blocks()`(여러 줄에 걸친 등기목적을 하나로 합쳐 통째로
`split_line_into_row()`에 넣는 방식) 자체였다**: 등기목적이 여러 줄에 걸친 갑구 행에서
합쳐진 텍스트 안의 "제N호" 접수번호가 원래보다 훨씬 뒤에서 나타나면서
`split_line_into_row()`의 receipt/cause/detail 경계가 밀렸다. 그 결과:
- "소유자 OOO"가 detail이 아니라 receipt에 남아 `_OWNER_PATTERN.search(detail)`이
  실패 — 소유권 이전 이력 전체가 유실.
- "채권최고액 금...원"도 같은 이유로 receipt에 남아 을구 근저당 합산이 (우연히
  결과값은 맞았지만) 잘못된 이유로 0이 되고 있었다.
- 등기부 하단의 "전산이기"(전산화 처리일)처럼 등기와 무관한 날짜가 `cause`로 잘못
  뽑히는 경우도 있었다.

**근본 수정** (`gapgu_ocr_row_parser.py`): "여러 줄을 합쳐서 한 번에 분할"하는 대신,
**순위번호로 시작하는 첫 줄만 `split_line_into_row()`로 분할**해 원래 컬럼 순서를
그대로 신뢰하고, 그 다음에 이어지는 줄들은 무조건 `detail` 뒤에 이어붙이는 방식
(`_group_lines_into_rows()`)으로 재설계했다. 이러면 receipt/cause 경계가 더 이상
밀리지 않아 소유자 이름/금액이 원래대로 detail에 남는다. 다만 "1번근저당권설정,"처럼
말소 참조가 등기목적 자체에 걸쳐 있는 경우, 어휘 매칭 시 "1번" 같은 순위번호 접두어가
같이 남도록 `split_line_into_row()`도 손봤고(전에는 어휘 단어만 남기고 접두어를
버렸다), `registry_parser.py`의 말소 판별(`_find_canceled_ranks`/`is_cancellation_entry`)
은 이제 purpose뿐 아니라 detail까지 합쳐서 검사하도록 맞췄다 — "말소"와 뒤쪽 순위번호가
이제 detail 쪽에 남기 때문이다. 추가로 `_OWNER_PATTERN`/`_AMOUNT_PATTERN` 검색 범위를
`receipt+detail` 합본으로 넓혀 이중 안전장치를 뒀다.

실키로 전체 문서(8페이지)를 처음부터 다시 돌려 최종 확인: `ownershipHistory` 5건
(국/이윤재/김수자/김하기/조춘근, 날짜까지 전부 원래 검증됐던 값과 정확히 일치) +
`eulguSeniorMortgageAmount: 0`(이번엔 "금액을 못 찾아서"가 아니라 "찾았지만 전부
말소돼서" 0이라는 것까지 확인됨). 회귀 테스트 4개 추가
(`test_gapgu_ocr_row_parser.py`/`test_registry_parser.py`), API 레이어 배선 테스트
4개 추가(`test_api.py`), `full_assessment.py` 교차검증 테스트 3개 추가
(`test_full_assessment.py`). 백엔드 전체 312개 테스트 통과.

**교훈**: 실키 검증은 "한 번 통과하면 끝"이 아니다 — 이번 세션에서만 같은 파일
(`gapgu_ocr_row_parser.py`)에 대한 수정이 서로 다른 실제 버그를 연쇄적으로 드러냈다.
한 문제(을구 여러 줄 말소)를 고치는 변경이 다른 부분(갑구 receipt/detail 경계)에
부작용을 낼 수 있으므로, 파서를 건드릴 때마다 전체 문서로 엔드투엔드 재검증하는 습관이
필요하다 — 유닛테스트만으로는 이런 상호작용을 못 잡는다(유닛테스트는 항상 통과했다).

### ✅ B2C 우선순위 확정 + 사기 패턴 위험 시각화 + 클로바 OCR 비용 방어 스위치 (2026-09-16)

로드맵 우선순위를 명확히 했다: **1단계 B2C 무료 버전을 먼저 완성·디버깅·출시해서 시장
반응을 본 뒤, 그 기반 위에 훨씬 프로페셔널한 B2B(공인중개사 대상 유료) 버전을 차후
별도 UI로 개발한다.** B2C는 고객에게 비용을 요구하지 않으므로 **운영비용이 0원이어야
한다**는 제약이 최우선이다.

- **`USE_CLOVA_OCR` 환경변수 추가** (`api.py`, `.env.example`) — `POST /registry/upload`가
  클로바 OCR(갑구 소유권 이전 이력, 유료)을 호출할지 결정하는 명시적 스위치. 기본값
  `false`. `registry_gapgu_ocr.py`는 원래 `CLOVA_OCR_INVOKE_URL`/`CLOVA_OCR_SECRET`이
  없으면 이미 no-op으로 빠지지만, 이 플래그는 그것과 별개의 이중 안전장치다 — 배포
  서버에 키가 실수로/테스트 목적으로 세팅돼 있어도 `USE_CLOVA_OCR=false`인 한 클로바
  API가 절대 호출되지 않는다. 이번에 완성한 클로바 갑구 파서 코드(`registry_gapgu_ocr.py`
  등)는 지우지 않고 이 플래그로 잠가서 자산으로 남겨뒀다 — 나중에 B2B 버전을 띄울 때
  `true`로 전환하면 바로 켜진다. 프론트(`Step2Documents.jsx`)에 "기본 vs 정밀" 같은
  모드 토글은 만들지 않았다 — B2C 화면은 단순해야 하므로 이 스위치는 순수하게 서버
  배포 설정으로만 존재한다. `test_api.py`에 `@patch("api.USE_CLOVA_OCR", True)`로
  갑구 OCR 경로를 검증하는 기존 테스트를 유지하고, 기본값(false)에서 클로바 API가
  아예 호출되지 않는지 확인하는 테스트(`test_clova_ocr_skipped_by_default_for_b2c`)를
  새로 추가했다.
- **`fraud_pattern_rules.detect_new_villa_recent_ownership_change()`에 필드 2개 추가**
  (`ownershipHistory`, `latestTransferDate`) — 판정 로직은 그대로고, 프론트가 소유권
  변동 타임라인을 그리는 데 필요한 데이터를 그대로/가공해 돌려주기만 한다(입력을
  그대로 echo하는 패턴은 `tenancy_safety_rules.check_possession_priority_gap_risk`가
  `moveInDate`/`rightsTimeline`을 돌려주는 것과 동일).
- **`Step3Result.jsx` 사기 패턴 위험 시각화** — `fraud.triggered`일 때:
  1. 상단 등급 배너 바로 아래 강한 헤드라인 배너("⚠️ 전형적인 전세사기 의심 패턴
     감지")를 상시 노출(아코디언에 숨기지 않음). 색상은 `overallGrade`가 danger까지
     escalate됐는지에 따라 빨강/주황으로 갈린다.
  2. "사기 패턴 탐지" 카드를 기본으로 펼친 상태로 시작(다른 카드는 기본 접힘).
  3. 새 컴포넌트 `OwnershipTimeline.jsx`(`PossessionTimeline.jsx`와 같은 원칙 —
     데이터 없는 지점은 추측해서 채우지 않고 아예 렌더링 안 함)로 "건물 완공(사용승인)
     → 최초 소유권 등록 → 소유권 이전(의심) → 현재 계약(입주) 시점"을 시간축으로
     보여주고, 의심되는 구간(`fraud.latestTransferDate`)으로 이어지는 선만 빨간
     점선으로 강조 + "⚠️ 사기 패턴 발생 구간" 태그를 붙인다.
  4. 정적 3단계 행동 가이드(이전 계약서 요구 → 완납증명서 확인 → 주변 시세 발품)를
     `FraudActionPlan`으로 고정 노출.
  - **B2C에서는 이 타임라인이 대부분 안 뜬다는 점에 주의** — `ownershipHistory`는
    클로바 OCR 결과인데 B2C는 `USE_CLOVA_OCR=false`라 항상 빈 배열이다. 즉 신축
    건물이어도 소유권 이전 이력 데이터가 없어 `fraud.triggered` 자체가 대부분
    안 켜진다(기존에도 이미 그랬던 상태 — 클로바 배선 전으로 되돌아간 것뿐, 새로운
    회귀 아님). B2B로 전환해 `USE_CLOVA_OCR=true`가 되는 순간 이 UI 전체가 살아난다.
  - `fraud_pattern_rules.py`/`test_fraud_pattern_rules.py`/`test_api.py` 포함
    백엔드 298개 테스트 전부 통과, 프론트 `npm run lint` / `npm run build` 통과.
    브라우저 실사용 확인은 위 "다음 세션 후보 태스크" 3번 참고(아직 못 함).

### ✅ 배포 직전 환경변수 점검 (2026-09-16 밤)

- `.env`/`.env.example` 변수 9개 목록 일치 확인, drift 없음.
- `.gitignore`/`.dockerignore`가 `.env`/`*.pdf`/`data/`/`*.db`/`*.pem`을 전부 제외 —
  비밀키·개인정보가 git이나 Docker 이미지에 안 들어감 확인.
- `docker-compose.yml`이 KAKAO/MOLIT/VWORLD 키와 `ASSESSMENT_DB_PATH`(볼륨 경로와
  일치하도록 명시적으로 고정된 값, 이전 세션에서 이미 잡은 버그)를 정상 전달.
- ⚠️ `USE_CLOVA_OCR`/`CLOVA_OCR_INVOKE_URL`/`CLOVA_OCR_SECRET`는 `docker-compose.yml`에
  아예 안 실려있다 — B2C 배포에선 오히려 안전(컨테이너 안에서 절대 켜질 수 없음)하지만,
  나중에 B2B로 이 스위치를 켤 때는 `docker-compose.yml`도 같이 고쳐야 한다는 걸
  잊기 쉬운 지점이니 그때 반드시 같이 확인할 것.

**SQLite(`data/assessments.db`) 백업은 의도적으로 안 함(2026-09-16 결정).** `./data`
볼륨은 컨테이너 재생성엔 살아남지만 진짜 백업(호스트 디스크 손상, 실수로 `data/` 삭제,
`docker compose down -v` 오발 등)은 없다 — 유실되면 진단 결과와 공유된 `/result/:id`
링크가 전부 깨진다. 다만 이 DB는 "진단 결과 캐시"일 뿐 유저 계정이나 유일한 원본
데이터가 아니라서(재진단하면 재생성 가능) 프로토타입 단계에서는 이 리스크를 감수하기로
결정했다. **실사용자가 늘어나 "링크가 갑자기 안 열린다" 항의가 실제로 발생하면 그때
백업 스크립트(cron으로 `data/assessments.db`를 볼륨 밖 다른 경로에 주기적으로 복사)를
추가할 것 — 지금 미리 만들지 않기로 함.**

### ✅ 을구 한글 숫자 금액표기 — 파서 대신 정직한 신호로 대응 (2026-09-16 밤)

브라우저 종단 테스트(A2)까지 마친 뒤 남은 B등급 과제로 "금일천오백육십만원정" 같은
한글 숫자 금액 표기를 조사했다. 결론: 새 한글 숫자 파서를 만들지 않기로 했다 —
실제 서비스에서 아직 유효한(말소 안 된) 근저당이 이 오래된 표기를 쓰는 빈도를 알 수
없어 투자 대비 효과를 판단할 근거가 부족하고, 파서를 만들어도 오탈자/이체 표기까지
전부 커버한다는 보장이 없다.

대신 이 프로젝트의 핵심 원칙("확인 안 된 걸 안전하다고 말하지 않는다")에 맞춰 **최소한
"놓쳤다는 사실 자체는 숨기지 않는" 방향으로 대응했다.** 기존 코드는 말소 안 된
근저당권의 채권최고액을 `_AMOUNT_PATTERN`(아라비아 숫자 전용)이 못 읽으면 그 행을
조용히 건너뛰었다 — 이러면 유효한 근저당이 선순위채권 합계에서 통째로 빠져 "거짓
안심"이 된다. `registry_parser.parse_eulgu()`에 `hasUnparsedMortgageAmount` 신호를
추가해, 말소 안 된 근저당의 금액을 못 읽으면 이 플래그를 세우도록 했다(말소된 근저당은
애초에 합산 대상이 아니므로 플래그 대상에서 제외 — 불필요한 경고로 헷갈리게 하지
않기 위함).

`registry_gapgu_ocr.py`(`eulguHasUnparsedMortgageAmount`) → `POST /registry/upload`
응답 → `POST /assessment`의 `eulgu_has_unparsed_mortgage_amount` → `full_assessment.py`
(계산된 `depositPriorityRisk`에 사후 반영, `check_deposit_priority_risk()` 시그니처는
안 건드림) → `overall_safety_assessment.py`(`priceIsEstimated`와 같은 패턴으로 caution
승격 + 안내 문구)까지 기존 을구 배선과 동일한 경로로 이어붙였다. 프론트
(`Step2Documents.jsx`)에도 노란색 경고 블록을 추가해 Step2 미리보기에서부터 바로 보이게
했다. 회귀 테스트 8개 추가(`registry_parser`/`registry_gapgu_ocr`/`full_assessment`/`api`
각 계층), 백엔드 전체 318개 테스트 통과.

### ✅ OWASP Top 10 기준 보안 점검 (2026-09-16 밤)

유저 요청으로 실제 코드베이스를 OWASP 관점에서 훑었다. 이미 괜찮았던 것: SQL
인젝션(SQLite 전부 파라미터 바인딩), 커맨드 인젝션(subprocess 전부 리스트 인자,
`shell=True` 없음), 비밀키 관리(`.env` git 히스토리에 커밋된 적 없음), 외부 API
호출 전부 `timeout` 명시, 예외 노출(전역 핸들러가 스택트레이스 대신 일반 메시지로
치환), ID 추측(uuid4 128비트), Pydantic `extra="forbid"`, stored XSS
(`dangerouslySetInnerHTML` 없음). 아래는 실제로 찾아서 고친 것들.

1. **[기능이 실제로 깨져 있던 버그] nginx `client_max_body_size` 미설정.** 기본값
   1MB인데 백엔드는 15MB PDF 업로드를 허용 — **실제 Docker 배포에서는 등기부 PDF
   업로드가 nginx 단계에서 413으로 막혀 애초에 동작하지 않았을 것이다.**
   `frontend/nginx.conf`에 `client_max_body_size 16m;` 추가.
2. **[OWASP API4:2023 Unrestricted Resource Consumption] 업로드 크기 체크가
   파일을 전부 읽은 "다음"에 일어남.** `api.py`의 `upload_registry_pdf()`가
   `file.file.read()`로 전체를 읽은 뒤에야 `MAX_REGISTRY_UPLOAD_BYTES` 초과 여부를
   확인했다 — 큰 파일을 반복 전송하면 디스크/CPU를 미리 소모시킬 수 있다. 1MB
   청크로 읽으면서 상한을 넘는 즉시 중단하도록 변경.
3. **[OWASP API4:2023] 모든 엔드포인트에 rate limiting이 전혀 없었음.** 회원가입/
   로그인이 없는 B2C 무료 버전이라 유저 구분 단서가 IP뿐 — `/assessment`(카카오/
   국토부/VWorld 쿼터 소모)와 `/registry/upload`(tesseract/poppler CPU 집약적) 둘
   다 무제한 반복 호출이 가능했다. 새 모듈 `rate_limiter.py`(인메모리 슬라이딩
   윈도우, IP+엔드포인트별 독립 카운터)로 `/assessment`는 IP당 분당 5회,
   `/registry/upload`는 IP당 분당 3회로 제한(429 반환). Redis 없이 프로세스 메모리
   dict로 구현 — 이 프로젝트가 아직 단일 워커 프로토타입이라는 전제는
   `assessment_store.py`(SQLite)와 동일. 여러 워커로 스케일하면 워커마다 카운터가
   따로 놀아 실질 허용량이 워커 수만큼 늘어나므로, 그때는 Redis로 옮겨야 한다.
4. **[3번을 실제로 작동시키기 위한 필수 후속 조치] `request.client.host`가 nginx
   뒤에서는 실제 클라이언트 IP가 아니라 nginx 컨테이너의 IP로 잡히는 문제.** 고치지
   않으면 rate limit이 "사이트 전체에 분당 N회"가 돼버려 사실상 무의미해진다.
   `nginx.conf`에 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`
   추가하고, `Dockerfile`의 uvicorn 실행에 `--proxy-headers
   --forwarded-allow-ips=*`를 추가해 그 헤더를 신뢰하도록 했다.
   ⚠️ **이 신뢰(`forwarded-allow-ips=*`)가 안전하려면 backend 컨테이너에
   nginx만 도달할 수 있어야 한다** — ~~지금 `docker-compose.yml`은
   `backend.ports: ["8000:8000"]`로 호스트에도 직접 노출돼 있어서, 이 상태로는
   누구나 백엔드를 nginx 없이 직접 두드리면서 `X-Forwarded-For`를 위조해 rate
   limit을 우회할 수 있다.~~ → **같은 날 바로 후속 조치 완료.** `backend.ports`를
   `expose: ["8000"]`로 바꿔 호스트에는 포트를 아예 안 열고 컴포즈 내부 네트워크
   에서만 접근 가능하게 했다 — frontend(nginx)는 어차피 컴포즈 내부 DNS
   (`http://backend:8000`)로 접속하므로 서비스는 그대로 동작한다(`docker compose
   config`로 검증). 로컬에서 `:8000/docs`로 직접 접근하던 편의는 이제 없다 —
   필요하면 `docker compose exec backend curl ...`로 확인할 것.

회귀 테스트: `test_rate_limiter.py`(신규, 5개) + `test_api.py`에 429 동작 확인
테스트 3개 추가, 기존 `/assessment`·`/registry/upload`를 여러 번 호출하는 테스트
클래스들은 매 테스트 전에 rate limiter를 리셋하는 `ResetRateLimiterMixin` 추가.
백엔드 전체 326개 테스트 통과.

### ✅ 2026-09-15 밤 세션에서 마지막 2개 외부 리소스 과제 전부 해결

지인이 NCP(네이버클라우드플랫폼) 한국 리전 서버(211.233.216.8, `yongtiger.pem`)와
클로바 OCR 키를 제공해줘서, README에 남아있던 마지막 두 블로커를 실제로 풀었다.
자세한 경위/버그는 아래 "VWorld 국내 서버 실배포 검증" / "클로바 OCR 실키 검증 —
소유권보존 갭 해결" 섹션 참고.

- [x] `debug_vworld_call.py`를 국내 서버 컨테이너 안에서 실행 — 싱가포르 IP 차단이
      국내 리전에서는 재현되지 않음을 확인, 실제 공시가격 데이터(서울 마포구 상암동)
      수신 확인
- [x] `POST /assessment` 엔드투엔드 검증 중 `public_price_adapter.py`의 실제 버그
      발견/수정 — 결과 0건일 때 vworld가 `<fields>` 태그를 아예 생략하는데, 이전
      코드는 이를 파싱 에러로 오분류했다 (`error` → `not_found`로 수정)
- [x] `debug_clova_ocr_call.py`를 실제 갑구 스캔 이미지(등기부등본_내아파트.pdf
      1페이지)로 실행 — 원본 응답 구조 확인, 줄 재조합/컬럼 분리 전부 실동작 검증
- [x] `gapgu_ocr_row_parser.split_line_into_row()`이 아니라 그 앞단
      `reconstruct_lines_from_clova_result()`의 `y_threshold`(12→30)가 실제 갭이었음을
      좌표로 확인하고 수정 — 순위번호가 두 줄로 쪼개진 셀 사이에 낄 때 소유권보존
      행 전체가 누락되던 버그 해결

---

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
- [x] Docker 배포 스캐폴딩 작성 (`Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`) →
      **2026-09-15 실빌드 검증 완료** (Docker Desktop 설치 후 `docker compose up --build`
      실행, SQLite 볼륨 영속성까지 확인 — 위 "Docker 배포 스캐폴딩" 섹션 참고)
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
- [x] 최우선변제금(③, 소액임차인 보호) 계산 — 부분적으로 보류 해제. 2026-09-15에 국가법령
      정보센터/법제처 찾기쉬운 생활법령정보/부동산케이스노트 3개 독립 출처로 교차 확인한
      **현행(2023-02-21 시행) 테이블만** `tenancy_safety_rules.check_minimum_priority_repayment()`
      로 구현 — 지역 4단계(서울/과밀억제권역·세종·용인·화성·김포/광역시·안산·경기광주·파주·
      이천·평택/그 밖의 지역)별 소액임차인 기준 보증금과 최우선변제금액, "주택가액의 1/2
      초과 금지" 상한까지 반영. 신규 모듈 `priority_region_classifier.py`가 주소 문자열을
      지역 등급으로 분류하는데, 남양주시(특정 10개 동만)/시흥시(반월특수지역만 제외)/인천
      서구(특정 8개 동+경제자유구역+남동산단 제외)처럼 시/군 "일부 동"만 걸치는 지역은
      주소만으로 정밀 판정이 안 돼 의도적으로 `None`(unknown)을 반환한다. 기준일(가장
      오래된 선순위 담보물권 접수일, 없으면 진단일)이 2023-02-21보다 이르면 — 즉 그 이전
      개정 이력(최소 7차례, 1984~2021년)의 금액 테이블은 아직 확보/검증 못 했으므로 —
      역시 unknown으로 정직하게 떨어진다. 이 룰은 다른 4개 룰과 성격이 달라(위험 신호가
      아니라 "이만큼은 보호받는다"는 안내) `overall_safety_assessment.py`의 등급 산정에는
      관여하지 않음 — 순수 정보 제공용 카드로만 Step3에 노출. 실제 서버로 성남시 야탑동
      주소 엔드투엔드 검증 완료(과밀억제권역 판정 → 4,800만원 정확히 산출). 백엔드 테스트
      230→266개 전부 통과. ⚠️ 남은 과제: 2023-02-21 이전 개정 이력 테이블 확보(과거
      기준일 케이스 대응), 남양주/시흥/인천서구의 동 단위 정밀 판정.
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
      배선(`_trade_fetch_fn_for()`). ✅ **실키로 검증 완료** (2026-09-15, data.go.kr에서
      두 API 상품 활용신청 승인 후 `debug_villa_officetel_call.py`를 실제 승인 키로 실행,
      LAWD_CD=11680/DEAL_YMD=202508) — mhouseNm(연립다세대 매물명)/offiNm(오피스텔
      매물명)/dealAmount/excluUseAr/umdNm/dealYear·Month·Day/cdealType/floor/jibun 전부
      실제 응답과 정확히 일치함을 확인. 이 코드를 처음 짤 때 세션 중 태그명 정보가 엇갈려서
      (한글 태그 주장 vs 영문 태그 주장) GitHub의 독립 오픈소스 MOLIT 클라이언트
      (tae0y/real-estate-mcp)로 먼저 교차검증했었는데, 실제 응답도 정확히 그 구조와
      일치했다. 덤으로 연립다세대 응답에만 있는 `houseType`("연립"|"다세대") 필드를
      새로 파싱 결과에 포함시킴. 실제 응답 기반 회귀 테스트(`XML_REAL_CAPTURED_VILLA`/
      `OFFICETEL`)를 `test_real_transaction_price_adapter.py`에 추가.
- [x] Docker 배포 인프라 고도화 — (1) `docker-compose.yml`에 `VWORLD_API_KEY`/
      `VWORLD_DOMAIN` 환경변수가 아예 안 넘어가던 버그 발견/수정(로컬에서 검증해둔 VWorld
      연동이 Docker 배포에서는 항상 꺼져있었을 것). (2) `POST /assessment`의 저장소를
      인메모리 dict에서 SQLite(`assessment_store.py`, 표준 라이브러리 sqlite3만 사용, 신규
      의존성 없음)로 전환 — 컨테이너 재시작/재배포마다 `/result/:id` 공유 링크가 전부
      깨지던 문제 해결. `docker-compose.yml`에 `./data:/app/data` 볼륨 마운트 추가로
      영속성 확보, `.gitignore`에 `data/`/`*.db` 추가. Redis는 여러 워커/여러 서버로
      스케일할 때 옮길 다음 단계로 남겨둠(지금은 단일 워커 프로토타입이라 별도 서비스
      운영 부담이 이득보다 큼). (3) `assessment_store.py`의 DB 경로 기본값(상대경로
      "data/assessments.db")이 볼륨 마운트 지점과 실제로는 `Dockerfile`의 `WORKDIR`에
      우연히 의존해서 맞아떨어지는 상태였음을 재검토로 발견 — `docker-compose.yml`에
      `ASSESSMENT_DB_PATH=/app/data/assessments.db`를 명시해 그 암묵적 결합을 없앰
      (커밋 `6afb4f2`). ⚠️ 이 머신엔 Docker가 없어 실제 빌드/컨테이너 재시작 시나리오
      자체는 여전히 미검증 — 정적 코드 검토 + SQLite 유닛테스트로만 확인함. 위 "🎯 지금
      최우선" 항목 참고. (villa/officetel 연동 포함) 백엔드 테스트 204→227개 전부 통과.
- [x] 실제 서버/클라우드에 배포 — 지인이 제공한 NCP 국내 리전 서버(211.233.216.8)에
      `deploy.bat`로 실제 배포 완료(2026-09-15 밤). Docker 볼륨/env 변경사항 전부
      실제 환경에서 정상 동작 확인. 위 "VWorld 국내 서버 실배포 검증" 섹션 참고.
      ⚠️ 임시 검증용 서버라 프로덕션 배포 타깃(도메인/HTTPS/스케일링)은 여전히 미정.
- [x] VWorld 국내 리전 실검증 + 클로바 OCR 실키 검증 — README의 마지막 외부 리소스
      블로커 2개 모두 해소(2026-09-15 밤). `public_price_adapter.py`의 `<fields>`
      태그 생략 버그, `gapgu_ocr_row_parser.py`의 `y_threshold` 버그 둘 다 실키로
      검증하며 발견/수정. 백엔드 테스트 286→288개 전부 통과.

---
**최근 업데이트**: 2026-09-16 세션 — **클로바 OCR 갑구 파서를 `POST /registry/upload`에
정식 배선하고, 실제 PDF+실키로 라우터 → `parse_gapgu()` → `fraud_pattern_rules.py` →
`/assessment` 전 구간을 엔드투엔드 검증 완료.** 갑구 페이지를 tesseract 마커로
사전 판별하려던 시도가 배경무늬 때문에 신뢰할 수 없다는 걸 확인하고, 대신 요약 페이지를
제외한 모든 페이지를 클로바에 보내고 `parse_gapgu()`의 키워드 필터링에 노이즈 제거를
맡기는 쪽으로 설계했다(`registry_gapgu_ocr.py` 신설, `registry_summary_ocr.py`의 페이지
렌더링 로직을 공개 함수로 리팩터링해 재사용). 실제 등기부 PDF로 검증하다가 진짜 버그를
하나 발견/수정했다 — 등기목적 칸이 좁아 "공유자전원지분전부이전"이 두 줄로 쪼개져 인쇄된
문서에서, "이전"만 있는 둘째 줄이 순위번호가 없어 노이즈로 걸러지는 바람에 최종 소유자
변경 이력 자체가 통째로 누락되고 있었다(`registry_parser.parse_gapgu()`의 키워드 매칭에
"지분전부" 추가로 해결). 신축+최근 소유권 변경 사기 패턴이 실제 데이터로 정확히
트리거/비트리거되는 것까지 `TestClient`로 확인했고, `Step2Documents.jsx`/`App.jsx`에
최소 프론트 배선(미리보기 표시 + `/assessment` 전달)도 마쳤다. 부수적으로
`run_all_tests.py`의 요약 출력이 Windows 콘솔에서 크래시하던 것도 고쳤다. 자세한 경위는
"클로바 OCR 갑구 파서 라우터 배선 + 실키 엔드투엔드 검증" 섹션 참고. 백엔드 테스트
288→296개 전부 통과, 프론트 lint/build 클린.

---
**이전 업데이트**: 2026-09-15 밤 세션 — **VWorld/클로바 OCR 실키 검증 완료, 마지막
외부 리소스 블로커 해소.** 지인이 NCP 국내 리전 서버(211.233.216.8)와 클로바 OCR
키를 제공해줘서 진행. 서버 접속 과정에서 NCP가 AWS와 다르다는 걸 여러 번 확인하며
헤맸다 — 기본 계정이 `ubuntu`가 아니라 `root`, 키 페어는 SSH pubkey가 아니라 초기
비밀번호 복호화용이라 비밀번호로 1회 로그인해서 공개키를 수동 등록해야 했음(등록 후
비밀번호 로그인은 비활성화). `deploy.bat`도 이 과정에서 계정명/`index.html` 누락 등
여러 버그를 고쳤다. 배포 후 컨테이너 안에서 `debug_vworld_call.py`를 실행해 이 개발
머신에서 계속 막혀있던 vworld API가 국내 리전에선 정상 동작함을 확인했고, 같은 세션에
클로바 OCR도 실제 등기부 이미지로 처음 검증했다. 두 검증 과정에서 각각 실제 버그를
하나씩 발견해 고쳤다 — VWorld는 "결과 0건일 때 `<fields>` 태그가 생략되는 걸 파싱
에러로 오분류"하던 버그, 클로바는 "순위번호가 두 줄로 쪼개진 셀 사이에 낄 때 그 행
전체가 누락"되던 `y_threshold` 버그(소유권보존 행 복구). 배포 인프라에서도
docker-compose v1의 `KeyError: 'ContainerConfig'` 재생성 버그를 발견해 우회법을
기록해뒀다. 자세한 경위는 각각 "VWorld 국내 서버 실배포 검증" / "클로바 OCR 실키
검증" 섹션 참고. 백엔드 테스트 286→288개 전부 통과.

---
**이전 업데이트**: 2026-09-15 저녁 세션 — **Docker 실빌드 검증 완료.** 이 개발
머신(Windows 11 Home)에 Docker Desktop을 처음 설치(관리자 권한 없이 사용자 레벨
설치 — `AppData\Local\Programs\DockerDesktop`, WSL2 백엔드는 이미 구성돼 있었음)하고
`docker compose build`/`up`을 실제로 돌렸다. 결과: 백엔드/프론트엔드 이미지 둘 다
빌드 성공, `pdfplumber`/`tesseract-ocr`/`poppler-utils` 전부 문제없이 설치됨(이
프로젝트가 가장 걱정했던 지점). 실제 카카오/국토부 키로 `POST /assessment`
엔드투엔드 성공. 결정적으로 — 낮 세션에 고친 `ASSESSMENT_DB_PATH` 명시 고정(커밋
`6afb4f2`)을 `docker compose down && up`(컨테이너 완전 재생성)으로 실제 검증:
`./data/assessments.db`가 호스트에 생성되고, 재생성 후에도 `GET /assessment/{id}`
결과가 그대로 살아있음을 확인. `docker exec`로 컨테이너 안 tesseract(5.5.0, kor
언어팩)/poppler 실행도 직접 확인. 이걸로 README의 "🎯 지금 최우선" 3개 과제 중
Docker 항목 완료 — 남은 건 VWorld(국내 리전 서버)와 클로바 OCR(NCP 키) 2개뿐.
백엔드 테스트/코드 변경 없음(순수 인프라 실행 검증).

---
**이전 업데이트**: 2026-09-15 세션 추가분(4) — 등기부 본문(갑구) 소유권 이전 이력 확보
경로에 네이버 클로바 OCR 연동 설계+로직 착수(위 "네이버 클로바 OCR 연동 설계" 섹션
참고). 핵심 발견: `registry_parser.py`의 `parse_gapgu()`/`parse_eulgu()`가 이미
완성돼 있고 테스트 12개가 통과한 상태였다는 것 — 새로 만들 건 판별 로직이 아니라
"스캔 이미지 → rank/purpose/receipt/cause/detail 딕셔너리"로 가는 앞단뿐이었다.
`clova_ocr_adapter.py`(네트워크 호출, 키 없으면 안전한 no-op)와
`gapgu_ocr_row_parser.py`(좌표 기반 줄 재조합은 순수 기하 계산이라 신뢰도 높음,
5개 컬럼 분리는 실제 응답 못 본 채 만들어서 미검증)로 나눠 구현. 구현 중 회귀
테스트로 실제 버그 하나 발견/수정: "말소" 기록의 등기목적을 어휘 매칭으로 축약하면
"말소" 텍스트가 잘려나가 취소 판별 자체가 깨지는 문제. `debug_clova_ocr_call.py`를
실키 검증용으로 준비해뒀지만 아직 Naver Cloud Platform 계정/키가 없어 실행은 못 함.
백엔드 테스트 266→286개 전부 통과(전부 모킹/합성 fixture 기반).

---
**이전 업데이트**: 2026-09-15 세션 추가분(3) — 최우선변제금(소액임차인 보호) 계산 부분
착수. 지금까지 "확인된 법정 테이블이 없어 의도적으로 보류"로 남겨뒀던 항목인데, 국가법령
정보센터/법제처/부동산케이스노트 3개 독립 출처를 웹서치로 교차 확인해 현행(2023-02-21
시행) 테이블만 우선 구현했다. 신규 모듈 `priority_region_classifier.py`(주소→지역등급
분류, 시/군 일부 동만 걸치는 예외지역은 명시적으로 unknown 반환)와
`tenancy_safety_rules.check_minimum_priority_repayment()`(룰 5, 기준일 판정+금액
계산+1/2 상한)를 추가하고 `full_assessment.py`에 배선, Step3에 정보성 카드로 노출.
이 룰은 위험 신호가 아니라 보호 안내라서 등급 산정에는 관여하지 않는다. 2023-02-21
이전 개정 이력(1984~2021년 최소 7차례)은 여전히 미확보라 그 이전 기준일은 unknown으로
정직하게 처리 — "부분 보류 해제"이지 완전 해결은 아니다. 실제 서버로 성남시 야탑동
주소 엔드투엔드 검증 완료. 백엔드 테스트 230→266개 전부 통과, 프론트 lint/build 클린.

---
**이전 업데이트**: 2026-09-15 세션 추가분(2) — 연립다세대/오피스텔 국토부 API 실키 검증
완료. data.go.kr에서 RTMSDataSvcRHTrade/RTMSDataSvcOffiTrade 두 API 상품 활용신청이
승인된 직후 `debug_villa_officetel_call.py`를 실제 키로 실행(LAWD_CD=11680,
DEAL_YMD=202508) — mhouseNm/offiNm/dealAmount/excluUseAr/umdNm 등 기존에 "개연성이
높다"고만 판단했던 태그 가정이 전부 실제 응답과 정확히 일치함을 확인했다. 스크립트
자체도 두 가지 버그를 고쳤다: `.env`를 안 읽어서(`load_dotenv()` 누락) 키가 항상
비어있던 것으로 뜬 문제, 그리고 경고 이모지(⚠️)가 이 Windows 터미널의 cp949 콘솔
인코딩에서 `UnicodeEncodeError`로 죽던 문제. 연립다세대 응답에서 새로 발견한
`houseType`("연립"|"다세대") 필드도 파싱 결과에 추가. 실제 캡처된 응답을 회귀
테스트(`XML_REAL_CAPTURED_VILLA`/`OFFICETEL`)로 고정해서 `real_transaction_price_adapter.py`
모듈 docstring의 "⚠️ 미검증" 경고를 전부 "✅ 검증 완료"로 바꿈. 백엔드 테스트 227→230개
전부 통과.

---
**이전 업데이트**: 2026-09-15 세션 추가분 (커밋 `6afb4f2`) — SQLite DB 경로를
`docker-compose.yml`에서 `ASSESSMENT_DB_PATH=/app/data/assessments.db`로 명시 고정.
직전 커밋에서 볼륨(`./data:/app/data`)은 추가했지만 `assessment_store.py`의 기본
경로(상대경로 "data/assessments.db")는 `Dockerfile`의 `WORKDIR /app`과 우연히
맞아떨어지는 암묵적 의존 상태였다 — 나중에 WORKDIR나 실행 방식(예: gunicorn)이
바뀌면 조용히 볼륨 밖에 DB가 생겨 재배포마다 데이터가 사라지는 버그가 재발할 수 있는
구조였음. 환경변수로 명시해 그 암묵적 결합을 제거함. 코드 변경 없이 설정 파일 한 줄이라
테스트 개수 변화는 없음(204→227 유지). "다음 단계"를 "실제 Docker 빌드 + 국내 리전
실서버 배포/검증" 하나의 흐름으로 재정리(아래 "🎯 지금 최우선" 참고) — 지금부터는 로직
추가보다 실제 환경 확보가 막고 있는 항목들을 뚫는 게 우선.

---
**이전 업데이트**: 2026-09-15 세션 — 세 갈래 작업. ① Docker 배포 정적 검토 중
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
