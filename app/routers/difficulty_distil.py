import logging
from fastapi import APIRouter, HTTPException
import sys, os, re

from app.routers.proto import parse_json_response

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from pydantic import BaseModel

from services.difficulty_service_distil2.difficulty_graph import run
from services.difficulty_service_distil2.seteuk_topic import recommend_topics

class TopicModel(BaseModel):
    major: str
    keyword: str
    seteuk_depth: str

class GraphModel(BaseModel):
    major: str
    keyword: object
    topic: str
    seteuk_depth: str

router = APIRouter(
    prefix="/seteukDifficulty_distil"
)

@router.post("/topic")
async def topic_gen(payload: TopicModel):
    major = payload.major
    keyword = payload.keyword
    seteuk_depth = payload.seteuk_depth
    depth_dict = {'기초': 'Basic', '응용': 'Applied','심화':'Advanced'}
    return recommend_topics(major, keyword, depth_dict[seteuk_depth])


@router.post("/guidelines")
async def protoGenerator(payload: GraphModel):
    major = payload.major
    keyword = payload.keyword
    topic = payload.topic
    seteuk_depth = payload.seteuk_depth
    depth_dict = {'기초': 'Basic', '응용': 'Applied','심화':'Advanced'}

    try:
        response = run(major, keyword, topic, depth_dict[seteuk_depth])
    except Exception as e:
        raise HTTPException(
            status_code=getattr(e, 'status_code', 500),
            detail={
                "error": e.__class__.__name__,
                "message": str(e)
            }
        )

    return response
