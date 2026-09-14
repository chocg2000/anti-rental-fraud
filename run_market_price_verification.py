"""
실제 데이터로 시세 추정 로직(market_price_estimator) 검증
-------------------------------------------------------------
국토부 API에서 실제 거래 데이터를 가져온 뒤, 특정 평형의 대표 시세가
market_price_estimator를 통해 제대로 뽑히는지 눈으로 확인한다.
"""

from datetime import date

from real_transaction_price_adapter import fetch_apt_trades
from market_price_estimator import estimate_market_price, _filter_trades, DEFAULT_AREA_TOLERANCE, RECENT_PERIOD_MONTHS

LAWD_CD = "11680"       # 강남구
DEAL_YMD = "202405"     # 2024년 5월
TARGET_AREA = 84.99     # 검증해볼 평형 (전용면적 ㎡) — 국민평형
AS_OF = date(2024, 6, 15)  # 이 날짜 기준으로 "최근 N개월"을 계산


def main():
    print(f"[요청] LAWD_CD={LAWD_CD}, DEAL_YMD={DEAL_YMD}, 대상 전용면적={TARGET_AREA}㎡\n")

    result = fetch_apt_trades(LAWD_CD, DEAL_YMD)

    if result["status"] != "ok":
        print(f"실거래 조회 실패: {result}")
        return

    trades = result["data"]
    print(f"전체 거래 {len(trades)}건 조회됨\n")

    # 1) 시세 추정 로직이 실제로 걸러내는 대상(동일 평형·최근 기간)을 눈으로 먼저 확인
    matched = _filter_trades(trades, TARGET_AREA, DEFAULT_AREA_TOLERANCE, AS_OF, RECENT_PERIOD_MONTHS)
    print(f"=== 1차 필터(±{DEFAULT_AREA_TOLERANCE}㎡, 최근 {RECENT_PERIOD_MONTHS}개월) 매칭 결과: {len(matched)}건 ===")
    for t in matched:
        print(f"  {t['dealYear']}.{t['dealMonth']}.{t['dealDay']} / {t['aptName']} "
              f"{t['exclusiveArea']}㎡ / {t['dealAmount']}만원 / {t['floor']}층")

    # 2) 실제 estimate_market_price() 결과
    print("\n=== estimate_market_price() 최종 결과 ===")
    estimate = estimate_market_price(trades, target_area=TARGET_AREA, as_of=AS_OF)
    for k, v in estimate.items():
        print(f"  {k}: {v}")

    # 3) 수작업 검산: 매칭된 거래들의 금액만 뽑아서 중위값을 눈으로도 확인
    if matched:
        amounts = sorted(t["dealAmount"] for t in matched)
        print(f"\n=== 검산용: 매칭된 거래 금액 정렬 ===\n  {amounts}")


if __name__ == "__main__":
    main()
