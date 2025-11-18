from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Union, Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from services.word_cloud import generate_word_cloud


class KeywordItem(BaseModel):
    keyword: str
    raw_weight: float


class WordCloudRequestModel(BaseModel):
    userId: Union[str, int]  # 사용자 ID (숫자 또는 문자열 허용)
    keywords: List[KeywordItem]  # 키워드 리스트
    font: Optional[int] = None  # 폰트 인덱스 (0-6, None이면 랜덤)
    color: Optional[int] = None  # 색상 테마 인덱스 (0-19, None이면 랜덤)
    mask: Optional[int] = None  # 마스크 인덱스 (None이면 직사각형)


router = APIRouter()


@router.post("/word-cloud")
async def create_word_cloud(payload: WordCloudRequestModel):
    """
    키워드 리스트로부터 워드 클라우드 이미지를 생성하는 엔드포인트

    Args:
        payload: 요청 데이터
            - userId: 사용자 ID
            - keywords: [{"keyword": "키워드", "raw_weight": 7.2}, ...] 형식의 키워드 리스트
            - font: 폰트 인덱스 (0-6, 생략 시 랜덤 선택)
            - color: 색상 테마 인덱스 (0-19, 생략 시 랜덤 선택)
            - mask: 마스크 인덱스 (생략 시 직사각형)

    Returns:
        StreamingResponse: PNG 형식의 워드 클라우드 이미지
    """
    try:
        # 키워드 리스트 검증
        if not payload.keywords:
            raise HTTPException(
                status_code=400,
                detail="키워드 리스트가 비어있습니다."
            )

        # 키워드 리스트를 딕셔너리 형태로 변환
        keywords_dict = [
            {"keyword": item.keyword, "raw_weight": item.raw_weight}
            for item in payload.keywords
        ]

        # 워드 클라우드 생성
        img_buffer = generate_word_cloud(
            keywords_dict,
            font=payload.font,
            color=payload.color,
            mask=payload.mask
        )

        # 이미지를 PNG로 반환
        return StreamingResponse(
            img_buffer,
            media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=wordcloud_{payload.userId}.png"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"워드 클라우드 생성 실패: {str(e)}")
