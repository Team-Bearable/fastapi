from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Optional, Union
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from services.keyword_extraction import extract_keywords


class GuidelineModel(BaseModel):
    introduction: str
    body: str
    conclusion: str


class KeywordExtractionModel(BaseModel):
    # 웹훅 기반 비동기 처리 필드
    historyId: Union[str, int]  # 필수: History ID (숫자 또는 문자열 허용)

    # 과목 정보 (topic 구성용)
    major: Optional[str] = None
    subject: Optional[str] = None
    subjectDetail: Optional[str] = None

    # 콘텐츠 필드 (세 가지 방식 지원)
    guideline: Optional[GuidelineModel] = None  # 방식 1: guideline 객체 (권장)
    content: Optional[str] = None  # 방식 2: 전체 콘텐츠 하나로
    introduction: Optional[str] = None  # 방식 3: 분리된 형태 (하위호환)
    body: Optional[str] = None
    conclusion: Optional[str] = None


router = APIRouter()


@router.post("/keyword-extraction")
async def keyword_extraction(payload: KeywordExtractionModel):
    """
    세특 콘텐츠에서 빈도 기반 raw_weight가 부여된 키워드를 추출하는 엔드포인트
    (웹훅 기반 비동기 처리)

    Flow:
        1. NestJS가 History 생성 (historyId)
        2. LLM 서버로 요청 { historyId, guideline }
        3. LLM이 키워드 추출
        4. 웹훅으로 응답 { historyId, keywords }
        5. NestJS가 historyId로 조회하여 userId 등 자동 획득

    Args:
        payload: API 서버 요청 데이터
            - historyId (필수): History ID (웹훅 응답 시 식별자로 사용)
            - major, subject, subjectDetail: 과목 정보 (topic 구성에 사용)
            - guideline: {introduction, body, conclusion} 객체 (권장) 또는
            - content: 전체 콘텐츠 (하나의 문자열) 또는
            - introduction, body, conclusion: 분리된 콘텐츠 (하위호환)

    Returns:
        웹훅 응답용 데이터
        {
            "historyId": "123",
            "keywords": [
                {"keyword": "키워드1", "raw_weight": 7.2},
                {"keyword": "키워드2", "raw_weight": 4.8},
                ...
            ]
        }

    raw_weight 계산 방법:
        - 불용어(조사, 접속사, 일반 동사) 제거
        - 전체 콘텐츠에서 맥락 상 중요한 키워드의 가중치 계산
        - 주제/제목에 등장한 키워드는 가중치 × 2
        - 복합어(예: "안전 점검")는 구문 가중 반영 (× 1.2)
    """
    try:
        # topic 구성: major > subject > subjectDetail
        topic_parts = []
        if payload.major:
            topic_parts.append(payload.major)
        if payload.subject:
            topic_parts.append(payload.subject)
        if payload.subjectDetail:
            topic_parts.append(payload.subjectDetail)
        topic = " - ".join(topic_parts) if topic_parts else ""

        # 콘텐츠 처리: guideline > content > introduction/body/conclusion 순서
        if payload.guideline:
            # 방식 1: guideline 객체 (권장)
            introduction = payload.guideline.introduction
            body = payload.guideline.body
            conclusion = payload.guideline.conclusion
        elif payload.content:
            # 방식 2: content를 그대로 사용
            full_content = payload.content
            introduction = full_content
            body = full_content
            conclusion = full_content
        else:
            # 방식 3: 분리된 콘텐츠 사용 (하위호환)
            introduction = payload.introduction or ""
            body = payload.body or ""
            conclusion = payload.conclusion or ""

        # 최소한 하나의 콘텐츠는 있어야 함
        if not introduction and not body and not conclusion:
            raise HTTPException(
                status_code=400,
                detail="guideline, content 또는 introduction/body/conclusion 중 최소 하나는 필수입니다."
            )

        keywords = extract_keywords(
            topic=topic,
            introduction=introduction,
            body=body,
            conclusion=conclusion
        )

        # 웹훅 응답: historyId + keywords (historyId를 문자열로 통일)
        response_data = {
            "historyId": str(payload.historyId),
            "keywords": keywords
        }

        # 응답 로그 출력
        print(f"키워드 추출 완료 - historyId: {response_data['historyId']}")
        print(f"추출된 키워드 개수: {len(keywords)}")
        print(f"응답 데이터: {response_data}")

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"키워드 추출 실패: {str(e)}")
