@echo off
echo ===================================================
echo Windows - 한국 임시 검증 서버 안전 배포 스크립트 (v2)
echo ===================================================

:: 1. yongtiger.pem 키 파일 존재 확인
if not exist "yongtiger.pem" (
    echo [오류] 이 폴더에 yongtiger.pem 파일이 없습니다. 파일을 복사해 주세요.
    pause
    exit /b
)

:: 2. 한국 가상 서버 초기 인프라 세팅 (NCP 콘솔에서 확인한 계정은 root — Docker는
::    root면 그룹 권한 없이 바로 쓸 수 있어 usermod/sg 단계가 필요 없다)
echo [1/3] 한국 가상 서버 접속 및 Docker 인프라 구성 중...
ssh -i yongtiger.pem root@211.233.216.8 "apt-get update && apt-get install docker.io docker-compose -y"

:: 3. 서버에 앱 전용 디렉터리 생성
ssh -i yongtiger.pem root@211.233.216.8 "mkdir -p /root/jeonse-app"

:: 4. SCP 전송 리스크 최소화 (개인키, 대용량 바이너리, 캐시 배제)
echo [2/3] 필요한 소스코드 및 .env만 선별하여 서버로 전송 중...
:: 핵심 파이썬 소스코드 파일들 전송
scp -i yongtiger.pem ./*.py root@211.233.216.8:/root/jeonse-app/
:: 설정 파일 및 환경변수 전송
scp -i yongtiger.pem ./requirements.txt root@211.233.216.8:/root/jeonse-app/
scp -i yongtiger.pem ./.env root@211.233.216.8:/root/jeonse-app/
scp -i yongtiger.pem ./Dockerfile root@211.233.216.8:/root/jeonse-app/
scp -i yongtiger.pem ./docker-compose.yml root@211.233.216.8:/root/jeonse-app/

:: 프론트엔드 코드 전송 (node_modules 제외, 구조화된 파일만 전송)
echo 프론트엔드 소스 전송 중...
ssh -i yongtiger.pem root@211.233.216.8 "mkdir -p /root/jeonse-app/frontend"
scp -i yongtiger.pem ./frontend/package*.json root@211.233.216.8:/root/jeonse-app/frontend/
scp -i yongtiger.pem ./frontend/vite.config.js root@211.233.216.8:/root/jeonse-app/frontend/
scp -i yongtiger.pem ./frontend/nginx.conf root@211.233.216.8:/root/jeonse-app/frontend/
scp -i yongtiger.pem ./frontend/Dockerfile root@211.233.216.8:/root/jeonse-app/frontend/
scp -i yongtiger.pem ./frontend/index.html root@211.233.216.8:/root/jeonse-app/frontend/
:: 프론트엔드 실제 코드 디렉터리 통째로 전송 (컴포즈 빌드용)
scp -i yongtiger.pem -r ./frontend/src root@211.233.216.8:/root/jeonse-app/frontend/
scp -i yongtiger.pem -r ./frontend/public root@211.233.216.8:/root/jeonse-app/frontend/

:: 5. 서버에서 도커 컴포즈 구동
echo [3/3] 서버에서 Docker Compose 빌드 및 컨테이너 구동 중...
ssh -i yongtiger.pem root@211.233.216.8 "cd /root/jeonse-app && docker-compose up --build -d"

echo ===================================================
echo [완료] 배포가 끝났습니다! 컨테이너 상태를 확인합니다.
echo ===================================================
ssh -i yongtiger.pem root@211.233.216.8 "cd /root/jeonse-app && docker-compose ps"
pause
