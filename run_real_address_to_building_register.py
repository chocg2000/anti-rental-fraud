"""
실제 주소 -> AddressResolver -> 건축물대장 API 파라미터 자동 추출 + 조회
------------------------------------------------------------------------
Mocking 없이 카카오 API로 실제 주소를 정규화하고, 그 결과(PNU)로 바로
건축물대장 API까지 호출해서 결과를 보여준다.
"""

from address_resolver import resolve_address, AddressResolutionError
from building_register_adapter import fetch_building_register

TARGET_ADDRESS = "서울 종로구 혜화로5길 52"


def main():
    print(f"[입력 주소] {TARGET_ADDRESS}\n")

    try:
        normalized = resolve_address(TARGET_ADDRESS)
    except AddressResolutionError as e:
        print(f"[주소 정규화 실패] {e}")
        return

    print("=== AddressResolver 결과 ===")
    for k, v in normalized.items():
        print(f"  {k}: {v}")

    pnu = normalized.get("pnu")
    if not pnu:
        print("\n⚠️  PNU를 만들지 못했습니다 (지번이 특정되지 않은 검색 결과일 수 있습니다).")
        return

    legal_dong_code = normalized["legalDongCode"]
    sigungu_cd = legal_dong_code[:5]
    bjdong_cd = legal_dong_code[5:]
    plat_gb_cd = pnu[10]
    bun = pnu[11:15]
    ji = pnu[15:19]

    print(f"\n=== 건축물대장 API 파라미터로 변환 ===")
    print(f"  sigunguCd={sigungu_cd}, bjdongCd={bjdong_cd}, "
          f"platGbCd={plat_gb_cd}, bun={bun}, ji={ji}\n")

    result = fetch_building_register(sigungu_cd, bjdong_cd, plat_gb_cd, bun, ji)
    print(f"=== 건축물대장 조회 결과 === status = {result['status']}")

    if result["status"] == "ok":
        for b in result["data"]:
            print(f"\n  건물명: {b['bldName']}")
            print(f"  주용도: {b['mainPurpose']}")
            print(f"  기타용도: {b['etcPurpose']}")
            print(f"  대장구분: {b['registerKind']}")
            print(f"  사용승인일: {b['useApprovalDate']}")
            print(f"  세대수: {b['householdCount']}")
            print(f"  근생빌라 의심(주용도 기준): {b['isRegisteredAsNonResidential']}")
            print(f"  위반건축물 확인여부: {b['violationStatusConfirmed']} (원본값: {b['violationStatusRaw']})")
    else:
        print(f"  상세: {result}")


if __name__ == "__main__":
    main()
