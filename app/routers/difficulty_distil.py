import logging
from fastapi import APIRouter, HTTPException
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
import sys, os, ast, re
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.model import anthropic, gpt4o, gpt4o_mini, perple, perplexity_model
from utils.difficulty_prompt_distil2 import seteukBasicTopic
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
    #예시 초기화
    topic_example = ""
    tip_example = ""
    if seteuk_depth == "기초":
        topic_example = tp_cs.system_basic
        tip_example = tp_cs.example_basic
        print('난이도 기초')
    elif seteuk_depth == "응용":
        topic_example = tp_cs.system_applied
        tip_example = tp_cs.example_applied
        print('난이도 응용')
    elif seteuk_depth == "심화":
        topic_example = tp_cs.system_advanced
        tip_example = tp_cs.example_advanced
        print('난이도 심화')
    print('topic', topic_example)
    topic_chain  = {"difficulty_template": RunnablePassthrough(), "major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    topic_result = topic_chain.invoke({'difficulty_template': topic_example, 'major':major, 'keyword':keyword, 'seteuk_depth':depth_dict[seteuk_depth]})
    # json_result = eval(result)
    tip_chain = {"example":RunnablePassthrough(), "major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'topics': RunnablePassthrough()}|tip_prompt | anthropic | StrOutputParser()
    tip_result = tip_chain.invoke({'example': tip_example, 'major':major, 'keyword':keyword, 'topics':topic_result})
    print('팁결과',repr(tip_result))
    json_result = eval(tip_result)
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
