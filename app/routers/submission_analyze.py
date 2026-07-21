from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.submission_analyze import analyze_report


class ReportAnalyzeRequest(BaseModel):
    presignedUrl: str
    topic: Optional[str] = None
    masterCategory: Optional[str] = None
    subCategory: Optional[str] = None
    department: Optional[str] = None
    major: Optional[str] = None


class ReportAnalyzeResponse(BaseModel):
    summary: str
    review: str


router = APIRouter()


@router.post("/submission-analysis", response_model=ReportAnalyzeResponse)
async def submission_analyze(payload: ReportAnalyzeRequest):
    try:
        result = await analyze_report(
            presigned_url=payload.presignedUrl,
            topic=payload.topic,
            master_category=payload.masterCategory,
            sub_category=payload.subCategory,
            department=payload.department,
            major=payload.major,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
