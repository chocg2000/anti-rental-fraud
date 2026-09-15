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
2026-09-15 기준 **288개 테스트 전부 통과**.

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
**최근 업데이트**: 2026-09-15 밤 세션 — **VWorld/클로바 OCR 실키 검증 완료, 마지막
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
