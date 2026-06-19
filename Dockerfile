FROM python:3.12-slim

WORKDIR /app
ENV TZ=Asia/Seoul

RUN apt-get update && apt-get install -y \
    build-essential \
    && pip install --upgrade pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY fonts ./fonts

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
