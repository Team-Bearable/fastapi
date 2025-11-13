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


def extract_keywords(topic: str, introduction: str, body: str, conclusion: str) -> list:
    """
    세특 콘텐츠에서 빈도 기반 raw_weight가 부여된 키워드를 추출합니다.

    Args:
        topic: 주제/제목
        introduction: 도입부 텍스트
        body: 본문 텍스트
        conclusion: 결론 텍스트

    Returns:
        추출된 키워드와 raw_weight 리스트 [{"keyword": "키워드", "raw_weight": 7.2}, ...]
    """
    try:
        # 프롬프트 준비
        kw_prompt = KeywordExtractionPrompt()
        keyword_prompt = ChatPromptTemplate.from_messages([
            ("system", kw_prompt.system),
            ("user", kw_prompt.human)
        ])

        # 체인 구성
        keyword_chain = (
            {
                "topic": RunnablePassthrough(),
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
            "topic": topic if topic else "주제 없음",
            "introduction": introduction,
            "body": body,
            "conclusion": conclusion
        })

        # 결과 파싱
        keywords = parse_keyword_result(result)
        return keywords

    except Exception as e:
        print(f"키워드 추출 중 오류 발생: {e}")
        return []


def parse_keyword_result(result: str) -> list:
    """
    LLM 응답을 파싱하여 키워드와 raw_weight 리스트로 변환합니다.

    Args:
        result: LLM의 응답 문자열

    Returns:
        파싱된 키워드-raw_weight 리스트 [{"keyword": "키워드", "raw_weight": 0.8}, ...]
    """
    try:
        # 1. JSON 파싱 시도 (가장 정확한 방법)
        try:
            keywords = json.loads(result)
            if isinstance(keywords, list) and len(keywords) > 0:
                # 딕셔너리 형태인지 확인
                if isinstance(keywords[0], dict) and 'keyword' in keywords[0]:
                    # raw_weight 필드 정규화
                    for kw in keywords:
                        # raw_weight 또는 weight 필드를 raw_weight로 통일
                        if 'raw_weight' not in kw and 'weight' in kw:
                            kw['raw_weight'] = kw.pop('weight')
                        elif 'raw_weight' not in kw:
                            kw['raw_weight'] = 0.5
                        kw['raw_weight'] = float(kw['raw_weight'])
                    return keywords
        except:
            pass

        # 2. 대괄호로 둘러싸인 부분 찾기
        list_pattern = r'\[.*\]'
        match = re.search(list_pattern, result, re.DOTALL)

        if match:
            list_str = match.group(0)
            # 안전한 파싱 시도
            try:
                keywords = eval(list_str)
                if isinstance(keywords, list) and len(keywords) > 0:
                    # 딕셔너리 형태인지 확인
                    if isinstance(keywords[0], dict) and 'keyword' in keywords[0]:
                        # raw_weight 필드 정규화
                        for kw in keywords:
                            if 'raw_weight' not in kw and 'weight' in kw:
                                kw['raw_weight'] = kw.pop('weight')
                            elif 'raw_weight' not in kw:
                                kw['raw_weight'] = 0.5
                            kw['raw_weight'] = float(kw['raw_weight'])
                        return keywords
            except Exception as e:
                print(f"eval 파싱 실패: {e}")

        # 3. 딕셔너리 패턴 추출 시도 (raw_weight만)
        raw_weight_pattern = r'\{"keyword":\s*"([^"]+)",\s*"raw_weight":\s*([\d.]+)\}'
        matches = re.findall(raw_weight_pattern, result)
        if matches:
            return [{"keyword": kw, "raw_weight": float(w)} for kw, w in matches]

        # 4. 실패 시 빈 리스트 반환
        print(f"키워드 파싱 실패. 원본 결과: {result}")
        return []

    except Exception as e:
        print(f"키워드 파싱 중 오류: {e}")
        return []
