from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager

# 현재 디렉토리와 상위 디렉토리를 PYTHONPATH에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routers import proto, difficulty, difficulty_distil, keyword, word_cloud, submission_analyze  # 라우터 가져오기
from worker.config import WorkerConfig
from worker.consumer import StreamConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("main")
_consumer = StreamConsumer(WorkerConfig())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 백그라운드 태스크로 기동 — 소비 실패가 HTTP 서빙을 막지 않게 await 하지 않는다.
    task = asyncio.create_task(_consumer.start())
    logger.info("LLM stream consumer started in background")
    yield
    await _consumer.stop()
    task.cancel()
    logger.info("LLM stream consumer stopped")


app = FastAPI(lifespan=lifespan)

# 라우터 포함
app.include_router(proto.router)
app.include_router(difficulty.router)
app.include_router(difficulty_distil.router)
app.include_router(keyword.router)
app.include_router(word_cloud.router)
app.include_router(submission_analyze.router)
