FROM python:3.12

# 작업 디렉토리 설정
WORKDIR /app

# 소스 코드 복사
COPY app ./app
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 컨테이너 포트 노출
EXPOSE 8000

# FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
