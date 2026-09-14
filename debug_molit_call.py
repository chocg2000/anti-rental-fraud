"""
디버그용: 국토부 API를 어댑터 없이 직접 호출해서
진짜 에러 원인(SSL/타임아웃/연결거부 등)을 그대로 확인한다.
"""

import os
import requests

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "")

if not SERVICE_KEY:
    print("⚠️  MOLIT_SERVICE_KEY 환경변수가 비어있습니다. 먼저 설정해주세요.")
    exit(1)

urls_to_try = [
    "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
]

params = {
    "serviceKey": SERVICE_KEY,
    "LAWD_CD": "11680",
    "DEAL_YMD": "202405",
    "numOfRows": 10,
}

for url in urls_to_try:
    print(f"\n{'='*60}")
    print(f"시도: {url}")
    print('='*60)
    try:
        res = requests.get(url, params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답 앞부분:\n{res.text[:1000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")
