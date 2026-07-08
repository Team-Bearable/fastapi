from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import logging
import sys
import os
from contextlib import asynccontextmanager

# 현재 디렉토리와 상위 디렉토리를 PYTHONPATH에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routers import proto, difficulty, keyword, word_cloud, submission_analyze  # 라우터 가져오기
from worker.config import WorkerConfig
from worker.consumer import StreamConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 러닝 이벤트 루프 안에서 생성한다(redis 클라이언트 루프 바인딩). start()는 내부에서
    # 백그라운드 러너를 띄우고 즉시 반환하므로 Redis 장애가 HTTP 기동을 막지 않는다.
    consumer = StreamConsumer(WorkerConfig())
    await consumer.start()
    logger.info("LLM stream consumer started")
    yield
    await consumer.stop()
    logger.info("LLM stream consumer stopped")


app = FastAPI(lifespan=lifespan)

# 라우터 포함
app.include_router(proto.router)
app.include_router(difficulty.router)
app.include_router(keyword.router)
app.include_router(word_cloud.router)
app.include_router(submission_analyze.router)
