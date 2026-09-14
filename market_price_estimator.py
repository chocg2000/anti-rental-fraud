"""
시세 추정 로직 (Market Price Estimator)
------------------------------------------
RealTransactionPriceAdapter가 가져온 실거래 리스트에서,
'이 매물(특정 전용면적)'에 해당하는 대표 시세를 뽑아낸다.

핵심 설계 포인트:
1. 평균이 아니라 중위값(median)을 쓴다 — 로열층 프리미엄이나 급매 같은 이상치에
   덜 흔들리기 때문. (7절 설계문서의 "없는 데이터를 억지로 추정해서 안전이라고
   잘못 알려주면 안 된다"는 원칙과 같은 맥락 — 왜곡된 시세로 위험도를 오판하면 안 된다.)
2. 지리적 범위(같은 동 → 자치구 전체) · 면적 허용오차 · 조회 기간을 '단계적으로'
   넓혀가며 데이터를 찾는다. 좁을수록(같은 동네·같은 평형·최근) 신뢰도가 높다.
   ⚠️ 국토부 실거래가 API는 개별 거래에 좌표(위도/경도)를 주지 않는다. 그래서
   "반경 200m" 같은 진짜 거리 계산은 불가능하고, 대신 실거래 데이터에 있는
   "동(법정동)" 정보로 "같은 동네 우선 탐색"을 근사치로 구현한다.
3. 데이터가 아예 없으면 절대 억지로 숫자를 만들지 않고 "unavailable"을 반환한다.
"""

import statistics
from datetime import date
from typing import TypedDict


# ---- 튜닝 가능한 임계값들 (실제 서비스 운영하면서 조정 대상) ----
DEFAULT_AREA_TOLERANCE = 3.0    # ㎡, 같은 평형으로 볼 오차 범위
WIDE_AREA_TOLERANCE = 5.0       # ㎡, 데이터 부족 시 넓히는 오차 범위
RECENT_PERIOD_MONTHS = 6        # 가장 신뢰할 수 있는 최근 기간
MAX_PERIOD_MONTHS = 12          # 그래도 안 되면 넓히는 최대 기간
MIN_TRADES_FOR_HIGH_CONFIDENCE = 3  # 이 이상 거래가 있어야 '신뢰도 high'
PUBLIC_PRICE_MULTIPLIER = 1.4  # 공동주택 공시가격 현실화율(약 70%)의 역수 근사치


class MarketPriceEstimate(TypedDict):
    marketPrice: int | None       # 만원 단위, 데이터 없으면 None
    confidence: str               # "high" | "low" | "estimated_from_public_price" | "unavailable"
    usedTradeCount: int
    basis: str                    # 어떤 조건으로 계산됐는지 설명 (UX/로그용)


def _trade_date(trade: dict) -> date | None:
    """거래 dict의 년/월/일 문자열을 date 객체로 변환. 값이 없으면 None."""
    try:
        return date(int(trade["dealYear"]), int(trade["dealMonth"]), int(trade["dealDay"]))
    except (KeyError, ValueError, TypeError):
        return None


def _filter_trades(trades: list[dict], target_area: float, area_tolerance: float,
                    as_of: date, period_months: int, target_dong: str | None = None) -> list[dict]:
    """
    면적 허용오차 + 최근 N개월 조건으로 거래를 필터링한다.
    target_dong이 주어지면 같은 동(법정동)의 거래만 남긴다 — "반경 200m" 대신 쓰는
    현실적 근사치 (좌표 데이터가 없어 진짜 거리 계산 불가).
    """
    # 기간 컷오프: as_of 기준으로 대략 period_months개월 전 (윤년 등은 근사치로 충분)
    cutoff_year = as_of.year
    cutoff_month = as_of.month - period_months
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = date(cutoff_year, cutoff_month, 1)

    filtered = []
    for trade in trades:
        area = trade.get("exclusiveArea")
        if area is None or abs(area - target_area) > area_tolerance:
            continue

        trade_date = _trade_date(trade)
        if trade_date is None or trade_date < cutoff:
            continue

        if target_dong is not None and trade.get("dong") != target_dong:
            continue

        filtered.append(trade)

    return filtered


def _median_result(matched: list[dict], confidence: str, basis: str) -> MarketPriceEstimate:
    return {
        "marketPrice": round(statistics.median(t["dealAmount"] for t in matched)),
        "confidence": confidence,
        "usedTradeCount": len(matched),
        "basis": basis,
    }


def estimate_market_price(
    trades: list[dict],
    target_area: float,
    as_of: date | None = None,
    public_price: int | None = None,
    target_dong: str | None = None,
) -> MarketPriceEstimate:
    """
    실거래 리스트에서 target_area(전용면적, ㎡)에 해당하는 대표 시세를 추정한다.

    단계적으로 조건을 넓혀가며 데이터를 찾는다 (지리적 범위 → 면적 → 기간 순으로 완화):
      1단계: 같은 동 + 면적 오차 ±3㎡ + 최근 6개월, 3건 이상 → confidence "high"
      2단계: 같은 동 + 면적 오차 ±3㎡ + 최근 12개월, 3건 이상 → confidence "high"
      3단계: 자치구 전체 + 면적 오차 ±3㎡ + 최근 6개월, 3건 이상 → confidence "high"
      4단계: 자치구 전체 + 면적 오차 ±3㎡ + 최근 12개월, 3건 이상 → confidence "high"
      5단계: 자치구 전체 + 면적 오차 ±5㎡ + 최근 12개월, 1건 이상 → confidence "low"
      6단계: public_price가 주어졌다면 → 공시가격×1.4, confidence "estimated_from_public_price"
      7단계: 그마저도 없으면 → confidence "unavailable", marketPrice=None

    Args:
        public_price: 공동주택 공시가격 (만원 단위). 마지막 폴백에만 쓰인다.
        target_dong: 매물이 속한 법정동(예: "삼성동"). 주어지면 1~2단계에서
            "같은 동네 우선 탐색"을 시도한다. 국토부 API가 개별 거래 좌표를
            안 주기 때문에, "반경 200m" 대신 쓰는 현실적 근사치다.
            생략하면(None) 곧바로 자치구 전체(3단계)부터 시작한다.
    """
    if as_of is None:
        as_of = date.today()

    if not trades:
        return _public_price_fallback_or_unavailable(public_price)

    # 1~2단계 — 같은 동 우선 (target_dong이 주어진 경우만)
    if target_dong is not None:
        for period in (RECENT_PERIOD_MONTHS, MAX_PERIOD_MONTHS):
            matched = _filter_trades(trades, target_area, DEFAULT_AREA_TOLERANCE, as_of, period, target_dong)
            if len(matched) >= MIN_TRADES_FOR_HIGH_CONFIDENCE:
                return _median_result(
                    matched, "high",
                    f"같은 동({target_dong}) 내 동일 평형(±{DEFAULT_AREA_TOLERANCE}㎡) "
                    f"최근 {period}개월 거래 {len(matched)}건",
                )

    # 3~4단계 — 자치구 전체로 확대, 면적은 그대로
    for period in (RECENT_PERIOD_MONTHS, MAX_PERIOD_MONTHS):
        matched = _filter_trades(trades, target_area, DEFAULT_AREA_TOLERANCE, as_of, period)
        if len(matched) >= MIN_TRADES_FOR_HIGH_CONFIDENCE:
            scope_note = "같은 동 데이터 부족으로 자치구 전체까지 확대 — " if target_dong else ""
            return _median_result(
                matched, "high",
                f"{scope_note}동일 평형(±{DEFAULT_AREA_TOLERANCE}㎡) 최근 {period}개월 거래 {len(matched)}건",
            )

    # 5단계 — 면적 오차까지 넓힘, 신뢰도 낮음
    matched = _filter_trades(trades, target_area, WIDE_AREA_TOLERANCE, as_of, MAX_PERIOD_MONTHS)
    if matched:
        return _median_result(
            matched, "low",
            f"유사 평형(±{WIDE_AREA_TOLERANCE}㎡)까지 넓혀 최근 {MAX_PERIOD_MONTHS}개월 "
            f"거래 {len(matched)}건 — 신뢰도 낮음",
        )

    # 6~7단계 — 공시가격 폴백 (또는 최종 unavailable)
    return _public_price_fallback_or_unavailable(public_price)


def _public_price_fallback_or_unavailable(public_price: int | None) -> MarketPriceEstimate:
    """실거래 비교가능 데이터가 전혀 없을 때 마지막으로 시도하는 단계."""
    if public_price is not None and public_price > 0:
        estimated = round(public_price * PUBLIC_PRICE_MULTIPLIER)
        return {
            "marketPrice": estimated,
            "confidence": "estimated_from_public_price",
            "usedTradeCount": 0,
            "basis": f"실거래 비교 대상 없음 — 공시가격({public_price:,}만원) × {PUBLIC_PRICE_MULTIPLIER} 통계적 추정치 (실거래 아님, 참고용)",
        }

    return {"marketPrice": None, "confidence": "unavailable",
            "usedTradeCount": 0, "basis": "실거래 데이터도 공시가격도 없어 추정 불가"}
