"""활동 리포트 변환 서비스 — 원문(마크다운)을 생기부 기재 문체 활동 서술 1건으로 변환.

submission_analyze 와 동일하게 raw AsyncAnthropic 클라이언트 + Anthropic 구조화 출력(json_schema)을
쓴다(비블로킹 async). span(원문 오프셋)은 v1 범위 밖 — activityContent + promptVersion 만 반환한다.
"""

import json
from typing import Optional

from app.utils.model import ANTHROPIC_MODEL, anthropic_async
from app.utils.report_convert_prompt import SYSTEM, USER
from app.services.report_conversion.errors import ContentPolicyError, ConversionError

# 관측·회귀 추적용 프롬프트 버전 (결과에 실려 나간다).
PROMPT_VERSION = "convert-v1"

_OUTPUT_SCHEMA = {
    "format": {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "activityContent": {"type": "string"},
            },
            "required": ["activityContent"],
            "additionalProperties": False,
        },
    }
}


def _fmt_keywords(keywords: Optional[list]) -> str:
    if not keywords:
        return ""
    return ", ".join(str(k) for k in keywords)


async def convert_report(
    report_title: str,
    content: str,
    section: str,
    grade: int,
    sub_section: Optional[str] = None,
    semester: Optional[int] = None,
    course_name: Optional[str] = None,
    academic_field_name: Optional[str] = None,
    keywords: Optional[list] = None,
    desired_field: Optional[str] = None,
) -> dict:
    # null/누락 컨텍스트는 빈 문자열로 생략 처리(교과외 리포트는 course_name/academic_field_name 이 없다).
    user_message = USER.format(
        report_title=report_title or "",
        section=section or "",
        sub_section=sub_section or "",
        grade=grade if grade is not None else "",
        semester=semester if semester is not None else "",
        course_name=course_name or "",
        academic_field_name=academic_field_name or "",
        keywords=_fmt_keywords(keywords),
        desired_field=desired_field or "",
        content=content or "",
    )

    message = await anthropic_async.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=SYSTEM,
        output_config=_OUTPUT_SCHEMA,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}],
            }
        ],
    )

    # 콘텐츠 정책 차단은 억지 파싱하지 않고 전용 실패로 올린다.
    if getattr(message, "stop_reason", None) == "refusal":
        raise ContentPolicyError("생성 콘텐츠가 정책 위반으로 차단됨")

    parsed = json.loads(message.content[0].text)
    activity_content = (parsed.get("activityContent") or "").strip()
    # not-blank 계약(§4): 빈 값을 성공으로 발행하면 myfolio 도메인 가드가 거부하므로 명시적 실패로 돌린다.
    if not activity_content:
        raise ConversionError("변환할 활동 내용이 없음")

    return {"activityContent": activity_content, "promptVersion": PROMPT_VERSION}
