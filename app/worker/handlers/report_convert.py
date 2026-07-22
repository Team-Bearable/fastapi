"""활동 리포트 변환 jobType 처리기 — 요청 payload(dict) → 결과(dict).

myfolio(Java)와 맞춘 입출력 (docs/report_activity_conversion.md §3·§4):
- REPORT_CONVERT: {reportTitle, content, section, grade, subSection?, semester?, courseName?,
  academicFieldName?, keywords?, desiredField?}
  → {activityContent, promptVersion}

개인정보(memberId·리포트 id)는 payload 에 실리지 않는다 — 상관은 봉투의 requestId 로만(consumer 가 echo).
"""

from app.services.report_conversion import (
    convert_report,
    ContentPolicyError,
    ConversionError,
)
from app.worker.errors import InvalidPayload, JobFailed

_SECTIONS = {"SUBJECT", "EXTRACURRICULAR"}
_SUB_SECTIONS = {"CAREER", "AUTONOMOUS", "CLUB", "PROJECT_VOLUNTEER"}


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


async def handle_report_convert(payload: dict) -> dict:
    # 필드/enum 검증은 try 밖 — InvalidPayload 가 아래 도메인 catch 에 안 먹히게(wordcloud 패턴 동일).
    report_title = _require(payload, "reportTitle")
    content = _require(payload, "content")
    section = _require(payload, "section")
    grade = _require(payload, "grade")
    if section not in _SECTIONS:
        raise InvalidPayload(f"unsupported section: {section!r}")
    sub_section = payload.get("subSection")
    if sub_section is not None and sub_section not in _SUB_SECTIONS:
        raise InvalidPayload(f"unsupported subSection: {sub_section!r}")

    try:
        return await convert_report(
            report_title=report_title,
            content=content,
            section=section,
            grade=grade,
            sub_section=sub_section,
            semester=payload.get("semester"),
            course_name=payload.get("courseName"),
            academic_field_name=payload.get("academicFieldName"),
            keywords=payload.get("keywords"),
            desired_field=payload.get("desiredField"),
        )
    except ContentPolicyError as e:
        raise JobFailed("LLM_CONTENT_POLICY", str(e))
    except ConversionError as e:
        # 변환 불가(빈 잡담 등)는 입력 문제 → 계약서 §6.3 카탈로그의 LLM_INVALID_INPUT.
        raise JobFailed("LLM_INVALID_INPUT", str(e))
