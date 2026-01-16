# 1. 가볍고 안정적인 Python 3.9 slim 버전 사용 (버전은 프로젝트에 맞춰 수정 가능)
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
# (캐싱 효율을 위해 소스 코드보다 먼저 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 8000번 포트 노출 (FastAPI 기본 포트)
EXPOSE 8000

# 서버 실행 (app:app 부분은 실제 실행 파일명에 맞춰 수정 필요)
# 예: main.py 안에 app 객체가 있다면 main:app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]