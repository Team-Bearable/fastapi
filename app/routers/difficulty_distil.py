import logging
from fastapi import APIRouter, HTTPException
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
import sys, os, ast, re

from app.routers.proto import parse_json_response

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.model import anthropic, gpt4o, gpt4o_mini, perple, perplexity_model
from utils.difficulty_prompt_distil import seteukBasicTopic
from langchain_core.output_parsers import StrOutputParser
from fastapi import APIRouter
from pydantic import BaseModel

from services.difficulty_service_distil2.difficulty_graph import run

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
    tp_cs = seteukBasicTopic()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    tip_prompt = ChatPromptTemplate.from_messages(
        [
            ("user", tp_cs.tip)
        ]
    )
    topic_chain  = {"major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    topic_result = topic_chain.invoke({'major':major, 'keyword':keyword, 'seteuk_depth':depth_dict[seteuk_depth]})
    # json_result = eval(result)
    tip_chain = {"major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'topics': RunnablePassthrough()}|tip_prompt | anthropic | StrOutputParser()
    tip_result = tip_chain.invoke({'major':major, 'keyword':keyword, 'topics':topic_result})
    print('팁결과',repr(tip_result))
    json_result = ast.literal_eval(tip_result)
    print('타입', type(json_result))

    return json_result


@router.post("/guidelines")
async def protoGenerator(payload: GraphModel):
    major = payload.major
    keyword = payload.keyword 
    topic = payload.topic
    seteuk_depth = payload.seteuk_depth
    depth_dict = {'기초': 'Basic', '응용': 'Applied','심화':'Advanced'}
    response = run(major, keyword, topic, depth_dict[seteuk_depth])
    return response
