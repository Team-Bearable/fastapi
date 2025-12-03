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
    # 과목 정보 (topic 구성용)
    major: Optional[str] = None
    subject: Optional[str] = None
    subjectDetail: Optional[str] = None

    # 콘텐츠 필드
    guideline: GuidelineModel  # 필수: guideline 객체


router = APIRouter()


@router.post("/keyword-extraction")
async def keyword_extraction(payload: KeywordExtractionModel):
    """
    세특 콘텐츠에서 빈도 기반 raw_weight가 부여된 키워드를 추출하는 엔드포인트

    Args:
        payload: API 서버 요청 데이터
            - major, subject, subjectDetail: 전공/과목 (info 구성에 사용)
            - guideline (필수): {introduction, body, conclusion} 객체

    Returns:
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
    """
    try:
        # info 구성: major > subject > subjectDetail
        info_parts = []
        if payload.major:
            info_parts.append(payload.major)
        if payload.subject:
            info_parts.append(payload.subject)
        if payload.subjectDetail:
            info_parts.append(payload.subjectDetail)
        info = " - ".join(info_parts) if info_parts else ""

        # 콘텐츠 추출
        introduction = payload.guideline.introduction
        body = payload.guideline.body
        conclusion = payload.guideline.conclusion

        keywords = extract_keywords(
            info=info,
            introduction=introduction,
            body=body,
            conclusion=conclusion
        )

        response_data = {
            "historyId": str(payload.historyId),
            "keywords": keywords
        }

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"키워드 추출 실패: {str(e)}")
