# 백엔드(api.py, FastAPI) 프로덕션 이미지
FROM python:3.13-slim

# registry_summary_ocr.py가 subprocess로 직접 호출하는 실행파일들.
# apt-get으로 깔면 PATH에 자동으로 잡히므로 TESSERACT_CMD 등 환경변수는 필요 없다
# (Windows 로컬 개발 환경에서만 .env로 전체 경로를 오버라이드해야 했던 것과 대비됨).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-kor \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 이 프로젝트는 전부 평평한 구조(서브폴더 없음)라 최상위 .py만 복사하면 된다.
# frontend/, tools/, .env, *.pdf 등은 .dockerignore로 애초에 빌드 컨텍스트에서 제외됨.
COPY *.py ./

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
