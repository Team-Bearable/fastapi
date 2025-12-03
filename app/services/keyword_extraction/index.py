from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.model import anthropic
from utils.keyword_prompt import KeywordExtractionPrompt
import json
import re


def extract_keywords(info: str, introduction: str, body: str, conclusion: str) -> list:
    """
    세특 콘텐츠에서 빈도 기반 raw_weight가 부여된 키워드를 추출합니다.

    Args:
        info: 전공/과목
        introduction: 도입부 텍스트
        body: 본문 텍스트
        conclusion: 결론 텍스트

    Returns:
        추출된 키워드와 raw_weight 리스트 [{"keyword": "키워드", "raw_weight": 7.2}, ...]
    """
    # 프롬프트 준비
    kw_prompt = KeywordExtractionPrompt()
    keyword_prompt = ChatPromptTemplate.from_messages([
        ("system", kw_prompt.system),
        ("user", kw_prompt.human)
    ])

    # 체인 구성
    keyword_chain = (
            {
                "info": RunnablePassthrough(),
                "introduction": RunnablePassthrough(),
                "body": RunnablePassthrough(),
                "conclusion": RunnablePassthrough()
            }
            | keyword_prompt
            | anthropic
            | StrOutputParser()
    )

    # 키워드 추출 실행
    result = keyword_chain.invoke({
        "info": info if info else "전공/과목 없음",
        "introduction": introduction,
        "body": body,
        "conclusion": conclusion
    })

    # 결과 파싱
    return json.loads(result)
