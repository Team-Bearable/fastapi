import logging
from fastapi import APIRouter, HTTPException
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
import sys
import os
import ast
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.model import anthropic, gpt4o, gpt4o_mini, perple, perplexity_model
from utils.prompt import seteukBasicBodyTop, seteukBasicProto, perplexity_prompt, material_organizer
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

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

def process_result(result: str):
    """
    보다 견고한 proto 결과 파싱 로직
    
    1. 결과에서 ```와 "json" 등의 불필요한 부분을 제거합니다.
    2. ast.literal_eval로 파싱을 시도합니다.
    3. 실패하면 json.loads로 직접 파싱을 시도합니다.
    4. 여전히 실패하면, 결과 문자열 내 첫 번째 {와 마지막 } 사이의 부분 문자열을 추출하여 파싱합니다.
    5. 마지막 괄호 누락 등 간단한 오류가 있는 경우 보완합니다.
    
    모든 시도가 실패하면 ValueError를 발생시킵니다.
    """
    # 1. 기본 클린징
    cleaned = result.replace("```", "").replace("json", "").strip()

    # 2. ast.literal_eval 시도
    try:
        return ast.literal_eval(cleaned)
    except Exception as e:
        logging.debug("ast.literal_eval 실패: %s", e)

    # 3. json.loads 직접 시도
    try:
        return json.loads(cleaned)
    except Exception as e:
        logging.debug("json.loads 직접 시도 실패: %s", e)

    # 4. 문자열 내 { ~ } 사이만 추출
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidate = cleaned[start:end+1]
        try:
            return json.loads(candidate)
        except Exception as e:
            logging.debug("부분 문자열로 json.loads 실패: %s", e)

    # 5. 마지막 }가 누락된 경우 보완 시도 (단, {로 시작할 때만)
    if cleaned.startswith("{") and not cleaned.endswith("}"):
        try:
            candidate = cleaned + "}"
            return json.loads(candidate)
        except Exception as e:
            logging.debug("마지막 } 보완 후 파싱 실패: %s", e)

    # 모든 시도가 실패하면 예외 발생
    raise ValueError(f"proto 결과 파싱 실패. 원본: {result}")

def llm_material_organizer(major, topic, context, model):
    tp_cs = material_organizer()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt = (
        {"major": RunnablePassthrough(), "topic": RunnablePassthrough(), "context": RunnablePassthrough()}
        | topic_prompt | model | StrOutputParser()
    )
    result_gpt = chain_gpt.invoke({"major": major, "topic": topic, "context": context})
    return result_gpt

@router.post("/proto")
async def seteukProto(payload: RequestModel):
    # 입력값 준비
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
    chain_gpt = (
        {"major": RunnablePassthrough(), "keyword": RunnablePassthrough(), "topic": RunnablePassthrough()}
        | topic_prompt | anthropic | StrOutputParser()
    )
    try:
        result = chain_gpt.invoke({"major": major, "keyword": keyword, "topic": topic})
    except Exception as invoke_e:
        logging.error("LLM 호출 중 오류: %s", invoke_e)
        raise HTTPException(status_code=500, detail="LLM 호출에 실패했습니다.")
    
    try:
        json_result = process_result(result)
    except Exception as final_e:
        logging.error("proto 파싱 오류: %s", final_e)
        logging.error("proto 원본 결과: %s", result)
        raise HTTPException(status_code=500, detail=f"proto 파싱 오류: {final_e}")

    return {"response": json_result}

@router.post("/body")
async def seteuk_body(payload: BodyModel):
    topic = payload.topic
    proto = payload.proto
    case_result = payload.case_result

    try:
        proto = json.loads(proto)
    except Exception as e:
        logging.error("body에서 proto json 파싱 실패: %s", e)
        raise HTTPException(status_code=500, detail="body proto 파싱 오류")
    
    tp_cs = seteukBasicBodyTop()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain_gpt = (
        {"topic": RunnablePassthrough(), "proto": RunnablePassthrough()}
        | topic_prompt | anthropic | StrOutputParser()
    )
    try:
        result_gpt = chain_gpt.invoke({"topic": topic, "proto": proto["body"]})
    except Exception as e:
        logging.error("body 처리 오류: %s", e)
        raise HTTPException(status_code=500, detail="body 처리 중 오류 발생")
    
    answer = [proto["introduction"], result_gpt + "\n\n\n" + case_result, proto["conclusion"]]
    return {"response": answer}

@router.post("/perplexity")
async def perplexity(payload: RequestModel):
    major = payload.major
    keyword = payload.keyword
    topic = payload.topic
    
    prompt = perplexity_prompt(topic)
    perple_messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.user}
    ]
    try:
        response = perple.chat.completions.create(
            model=perplexity_model,
            messages=perple_messages
        )
        case_result = response.choices[0].message.content
        citations = response.citations
    except Exception as e:
        logging.error("perplexity 호출 오류: %s", e)
        raise HTTPException(status_code=500, detail="perplexity 호출 오류")
    
    while True:
        try:
            case = llm_material_organizer(major, topic, case_result, gpt4o)
            json_case = process_result(case)
            break
        except Exception as e:
            logging.error("perplexity json 파싱 오류: %s", e)
            # 무한루프 방지를 위해 적절한 재시도 횟수를 둘 수 있음.
            continue

    case_study = list(filter(lambda x: x["host"] != "no", json_case))
    applied_study = list(filter(lambda x: x["host"] == "no", json_case))
    reference_news = []
    case_study_str = "<관련 사례>\n"

    logging.info("citations: %s", citations)
    if len(case_study) > 0:
        for i in case_study:
            case_study_str += f"""
    * 사례: {i['topic']}
    * 내용: {i['content']}
    * 진행 기관: {i['host']}
    * 관련 자료 링크: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({
                "title": i["topic"],
                "institute": i["host"],
                "url": [citations[ii-1] for ii in eval(i["src"])][0],
                "date": None
            })
    else:
        case_study_str = ""

    applied_study_str = "<응용 탐구>\n"
    if len(applied_study) > 0:
        for i in applied_study:
            applied_study_str += f"""
    * 주제: {i['topic']}
    * 내용: {i['content']}
    * 관련 자료: {[citations[ii-1] for ii in eval(i['src'])]}
    """
            reference_news.append({
                "title": i["topic"],
                "institute": None,
                "url": [citations[ii-1] for ii in eval(i["src"])][0],
                "date": None
            })
    else:
        applied_study_str = ""

    return {"case_result": applied_study_str + "\n" + case_study_str, "reference_news": reference_news}
