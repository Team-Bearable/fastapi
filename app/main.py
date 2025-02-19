from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mangum import Mangum

import sys
import os

# 현재 디렉토리와 상위 디렉토리를 PYTHONPATH에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from routers import proto, difficulty  # 라우터 가져오기
app = FastAPI()

# 라우터 포함
app.include_router(proto.router)
app.include_router(difficulty.router)

# Mangum 객체 생성 (AWS Lambda 호환용)
handler = Mangum(app)
