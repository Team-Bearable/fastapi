from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from services.report_analyze import analyze_report


class ReportAnalyzeRequest(BaseModel):
    presignedUrl: str
    topic: Optional[str] = None
    masterCategory: Optional[str] = None
    subCategory: Optional[str] = None
    department: Optional[str] = None
    major: Optional[str] = None


class ReportAnalyzeResponse(BaseModel):
    summary: str
    opinion: str


router = APIRouter()


@router.post("/report-analyze", response_model=ReportAnalyzeResponse)
async def report_analyze(payload: ReportAnalyzeRequest):
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
