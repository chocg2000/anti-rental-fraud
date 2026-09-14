"""
E2E 회귀 테스트용 고정 fixture
--------------------------------
아래 데이터는 전부 2026-09-12 실제 API 호출로 확인했던 진짜 값이다 (조작/가상 데이터 아님).
API를 다시 호출하면 시간이 지나 값이 바뀔 수 있으므로, 회귀 테스트의 재현성을 위해
이 시점의 스냅샷을 그대로 고정해서 쓴다 — "코드를 고쳤을 때 결과가 달라졌는가"를
검증하는 게 목적이지, 최신 시세를 검증하는 게 목적이 아니기 때문이다.

주의: 실제 서비스에서 값이 바뀌면 이 fixture도 의도적으로 다시 캡처해서 갱신해야 한다
(그때는 왜 갱신했는지 커밋 메시지/주석에 남길 것).
"""

# ---- 카카오 AddressResolver 응답 (강남구 삼성동 159 — 실제로는 코엑스였음, 3.29일자 검증) ----
FAKE_KAKAO_RESPONSE_COEX = {
    "documents": [
        {
            "address_name": "서울 강남구 삼성동 159",
            "address": {
                "address_name": "서울 강남구 삼성동 159",
                "b_code": "1168010500",
                "mountain_yn": "N",
                "main_address_no": "159",
                "sub_address_no": "",
                "x": "127.062554",
                "y": "37.508845",
            },
            "road_address": {"address_name": "서울 강남구 테헤란로 427"},
            "x": "127.062554",
            "y": "37.508845",
        }
    ]
}

# ---- 실제 국토부 실거래가 API 응답 중 확인된 진짜 거래 20건 (2024년 5월, 강남구, 84㎡대) ----
# David님이 로컬에서 실행한 결과를 화면으로 직접 확인하고 옮겨 적은 값들.
REAL_GANGNAM_84_TRADES = [
    {"aptName": "신현대11차", "dealAmount": 690000, "exclusiveArea": 183.41, "dealYear": "2024", "dealMonth": "5", "dealDay": "17", "floor": "3"},
    {"aptName": "아크로힐스논현", "dealAmount": 201000, "exclusiveArea": 84.208, "dealYear": "2024", "dealMonth": "5", "dealDay": "31", "floor": "2"},
    {"aptName": "한양2", "dealAmount": 590000, "exclusiveArea": 175.92, "dealYear": "2024", "dealMonth": "5", "dealDay": "3", "floor": "10"},
    {"aptName": "경남", "dealAmount": 156500, "exclusiveArea": 59.76, "dealYear": "2024", "dealMonth": "5", "dealDay": "27", "floor": "3"},
    {"aptName": "럭키(963)", "dealAmount": 193000, "exclusiveArea": 84.97, "dealYear": "2024", "dealMonth": "5", "dealDay": "30", "floor": "9"},
    {"aptName": "선경1차(1동-7동)", "dealAmount": 310000, "exclusiveArea": 84.35, "dealYear": "2024", "dealMonth": "5", "dealDay": "21", "floor": "13"},
    {"aptName": "강남한양수자인(4단지)", "dealAmount": 145000, "exclusiveArea": 84.83, "dealYear": "2024", "dealMonth": "5", "dealDay": "24", "floor": "3"},
    {"aptName": "도곡렉슬", "dealAmount": 282000, "exclusiveArea": 84.9984, "dealYear": "2024", "dealMonth": "5", "dealDay": "25", "floor": "4"},
    {"aptName": "도곡렉슬", "dealAmount": 292000, "exclusiveArea": 84.9984, "dealYear": "2024", "dealMonth": "5", "dealDay": "22", "floor": "12"},
    {"aptName": "디에이치자이개포", "dealAmount": 280000, "exclusiveArea": 84.73, "dealYear": "2024", "dealMonth": "5", "dealDay": "17", "floor": "23"},
    {"aptName": "우성7", "dealAmount": 217000, "exclusiveArea": 83.69, "dealYear": "2024", "dealMonth": "5", "dealDay": "28", "floor": "3"},
    {"aptName": "래미안블레스티지", "dealAmount": 284000, "exclusiveArea": 84.94, "dealYear": "2024", "dealMonth": "5", "dealDay": "17", "floor": "26"},
    {"aptName": "디에이치아너힐즈", "dealAmount": 310000, "exclusiveArea": 84.3558, "dealYear": "2024", "dealMonth": "5", "dealDay": "15", "floor": "27"},
    {"aptName": "동현아파트1~6", "dealAmount": 202000, "exclusiveArea": 84.92, "dealYear": "2024", "dealMonth": "5", "dealDay": "21", "floor": "11"},
    {"aptName": "대치삼성", "dealAmount": 239000, "exclusiveArea": 84.58, "dealYear": "2024", "dealMonth": "5", "dealDay": "27", "floor": "2"},
    {"aptName": "개포래미안포레스트", "dealAmount": 258000, "exclusiveArea": 84.83, "dealYear": "2024", "dealMonth": "5", "dealDay": "18", "floor": "28"},
    {"aptName": "포이벨리", "dealAmount": 89000, "exclusiveArea": 84.69, "dealYear": "2024", "dealMonth": "5", "dealDay": "23", "floor": "2"},
    {"aptName": "역삼푸르지오", "dealAmount": 243000, "exclusiveArea": 84.9097, "dealYear": "2024", "dealMonth": "5", "dealDay": "18", "floor": "6"},
    {"aptName": "도곡렉슬", "dealAmount": 290000, "exclusiveArea": 84.9084, "dealYear": "2024", "dealMonth": "5", "dealDay": "14", "floor": "14"},
]

# ---- 실제 건축물대장 API 응답 (경기 성남시 분당구 야탑동 335 장미마을 822동 204호) ----
REAL_YATAP_BUILDING_INFO = {
    "bldName": "영은타운",
    "mainPurpose": "공동주택",
    "etcPurpose": "공동주택(다세대주택(29세대))",
    "registerKind": "표제부",
    "useApprovalDate": "20090211",
    "householdCount": "29",
    "isRegisteredAsNonResidential": False,
    "violationStatusRaw": None,
    "violationStatusConfirmed": False,
}

# ---- 실제 등기부등본 요약 페이지 OCR 원문 (경기 성남시 분당구 야탑동 335 장미마을 822동 204호) ----
REAL_YATAP_REGISTRY_OCR_TEXT = """즈     ,              ^     =
주요 등기사항 요약 (참고용)
[주의사항]
본 주요 둥기사항 요약은 중명서상에 말소되지 않은 사항을 간략히 요약한 것으로 증명서로서의 기능을 제공하지 않습니다.
실제 권리사항 파악을 위해서는 발급된 중명서를 필히 확인하시기 바랍니다.
고유번호 1356-1996-092460
[집합건물] 경기도 성남시 분당구 야탑동 335 장미마을 제822동 제2충 제204호
1. 소유지분현황 ( 갑구 )
조춘근 (소유자) | 670209-1788617 | 단독소유    경기도 성남시 분당구 장미로 101, 822동            5
204호(야탑동, 장미마을)
2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )
- 기록자항 없음
3. (근)저당권 및 전세권 등 ( 을구 )
11    전세권설정          2025년3월26일 | 전세금 _금300,000,000원                     조춘근
제1247861호  전세권자 주식회사지음이엔지
[참고사항]
가. 등기기록에서 유효한 지분을 가진 소유자 혹은 공유자 현황을 가나다 순으로 표시합니다.                      ,
"""
