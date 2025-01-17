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
from pydantic import BaseModel
import ast
import json
def json_format(response):
    response = response.replace("json", '')
    response = response.replace("```", '').strip()
    response = ast.literal_eval(response)
    return response

class RequestModel(BaseModel):
    major: str
    keyword: str
    topic: str

class BodyModel(BaseModel):
    topic: str
    proto: object
    case_result: str

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
    result = None    
    try:
        result = chain_gpt.invoke({'major':major, 'keyword':keyword, 'topic': topic})
    except Exception as e:
        print('proto 오류:', e)
    print('결과', result)
    json_result = json_format(result)
    return {"response":json_result}

@router.post("/body")
async def seteuk_body(payload: BodyModel):
    topic = payload.topic
    proto = payload.proto
    case_result = payload.case_result
    print('프로토 로그', proto)
    print('프로토 타입', type(proto))
    proto1 = json.loads(payload.proto)
    print('프로토 로그1', proto1)
    print('프로토 타입2', type(proto1))
    tp_cs = seteukBasicBodyTop()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt  = {"topic": RunnablePassthrough(), 'proto': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result_gpt = None
    try:
        result_gpt = chain_gpt.invoke({'topic':topic, 'proto':proto1['body']})
    except Exception as e:
        print('body 오류:', e)
    
    answer = [proto1['introduction'], result_gpt +'\n\n\n'+ case_result , proto1['conclusion']]
    return {'response': answer}

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
    try:
        response = perple.chat.completions.create(
            model = perplexity_model,
            messages = perple_messages
        )
        case_result = response.choices[0].message.content
        citations = response.citations
    except Exception as e:
        print('perplexity 오류:', e)
    while True:
        try:
            case = llm_material_organizer(major, topic, case_result, gpt4o)    
            json_case = json_format(case)
            break
        except Exception as e:
            print('perple json 오류:', e)
            continue
    case_study = list(filter(lambda x: x['host']!='no', json_case))
    applied_study = list(filter(lambda x: x['host']=='no', json_case))
    reference_news = []
    case_study_str = "<관련 사례>\n"
    if len(case_study) > 0:
        for i in case_study:
            case_study_str +=f"""
    * 사례: {i['topic']}
    * 내용: {i['content']}
    * 진행 기관: {i['host']}
    * 관련 자료 링크: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({'title': i['topic'],
                                   'institute': i['host'],
                                   'url': [citations[ii-1][0] for ii in eval(i['src'])],
                                   'date':None})
    else:
        case_study_str = ""

    applied_study_str = "<응용 탐구>\n"
    if len(applied_study) > 0:
        for i in applied_study:
            applied_study_str +=f"""
    * 주제: {i['topic']}
    * 내용: {i['content']}
    * 관련 자료: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({'title': i['topic'],
                                   'institute': None,
                                   'url': [citations[ii-1][0] for ii in eval(i['src'])],
                                   'date':None})
    else:
        applied_study_str = ""

    return {'case_result': applied_study_str + "\n" + case_study_str, 'reference_news': reference_news}

