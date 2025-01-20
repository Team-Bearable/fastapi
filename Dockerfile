FROM python:3.12

# 작업 디렉토리 설정
WORKDIR /app

# 소스 코드 복사
COPY app ./app
COPY requirements.txt .

# 빌드 시 환경 변수 전달
ARG ENV=development
ENV ENV=${ENV}

# 의존성 설치
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 컨테이너 포트 노출
EXPOSE 8000

# ENV에 따라 실행 명령 변경
CMD if [ "$ENV" = "local" ]; then \
        uvicorn app.main:app --host 0.0.0.0 --port 8000; \
    else \
        python -m awslambdaric app.main.handler; \
    fi
