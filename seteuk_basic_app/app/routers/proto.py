from fastapi import APIRouter
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.model import anthropic, gpt4o, gpt4o_mini, perple, perplexity_model
from utils.prompt import seteukBasicBodyTop, seteukBasicProto, perplexity_prompt, material_organizer
from langchain_core.output_parsers import StrOutputParser
from fastapi import APIRouter
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
import ast
def json_format(response):
    response = response.replace("json", '')
    response = response.replace("```", '').strip()
    response = ast.literal_eval(response)
    return response

class RequestModel(BaseModel):
    major: str
    keyword: str
    topic: str
router = APIRouter(
    prefix="/seteukBasic"
)

def llm_material_organizer(major, topic, context, model):
    tp_cs = material_organizer()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt  = {"major": RunnablePassthrough(), "topic": RunnablePassthrough(), 'context':RunnablePassthrough() }|topic_prompt | model | StrOutputParser()
    result_gpt = chain_gpt.invoke({'major': major, 'topic':topic, 'context': context})
    return result_gpt

@router.post("/proto")
async def seteukProto(payload: RequestModel):
    # 테스트용 기본 응답 데이터 생성
    major = payload.major
    keyword = payload.keyword
    topic = payload.topic

    tp_cs = seteukBasicProto()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt  = {"major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'topic': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()

    result = chain_gpt.invoke({'major':major, 'keyword':keyword, 'topic': topic})

    json_result = eval(result)
    return {"response":json_result}

@router.post("/body")
async def seteuk_body(payload):
    topic = payload.topic
    proto = payload.proto
    tp_cs = seteukBasicBodyTop()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt  = {"topic": RunnablePassthrough(), 'proto': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result_gpt = chain_gpt.invoke({'topic':topic, 'proto':proto})
    return result_gpt

@router.post("/perplexity")
async def perplexity(payload: RequestModel):
    # 테스트용 기본 응답 데이터 생성
    major = payload.major
    keyword = payload.keyword
    topic = payload.topic
    prompt = perplexity_prompt()
    perple_messages = [
        {"role": "system",
         "content": (prompt.system)},
        {"role": "user",
         "content": (prompt.user)}
    ]

    response = perple.chat.completions.create(
        model = perplexity_model,
        messages = perple_messages
    )
    case_result = response.choices[0].message.content
    citations = response.citations
    case = llm_material_organizer(major, topic, case_result, gpt4o)
    json_case = json_format(case)
    case_study = list(filter(lambda x: x['host']!='no', json_case))
    applied_study = list(filter(lambda x: x['host']=='no', json_case))

    case_study_str = "<관련 사례>\n"
    if len(case_study) > 0:
        for i in case_study:
            case_study_str +=f"""
    사례: {i['topic']}
    내용: {i['content']}
    진행 기관: {i['host']}
    관련 자료: {[citations[ii-1] for ii in eval(i['src'])]}
    """
    else:
        case_study_str = ""

    applied_study_str = "<응용 탐구>\n"
    if len(applied_study) > 0:
        for i in applied_study:
            applied_study_str +=f"""
    주제: {i['topic']}
    내용: {i['content']}
    관련 자료: {[citations[ii-1] for ii in eval(i['src'])]}
    """
    else:
        applied_study_str = ""

    return applied_study_str, case_study_str

