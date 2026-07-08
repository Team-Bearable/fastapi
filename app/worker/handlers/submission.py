"""제출물 분석 jobType 처리기 — 요청 payload(dict) → 결과(dict).

Java SubmissionAnalysisAdapter 와 맞춘 입출력:
- SUBMISSION_ANALYSIS: {presignedUrl, topic?, masterCategory?, subCategory?, department?, major?}
  → {summary, review}

원문 PDF 는 presignedUrl(S3) 로 워커가 직접 다운로드한다(메시지엔 본문 미포함).
"""

from services.submission_analyze import analyze_report
from worker.errors import InvalidPayload


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


async def handle_submission_analysis(payload: dict) -> dict:
    return await analyze_report(
        presigned_url=_require(payload, "presignedUrl"),
        topic=payload.get("topic"),
        master_category=payload.get("masterCategory"),
        sub_category=payload.get("subCategory"),
        department=payload.get("department"),
        major=payload.get("major"),
    )
