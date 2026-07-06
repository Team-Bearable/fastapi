"""구조화 태깅 — 활동 1건을 LLM으로 태깅해 student_tagged 속성 24개를 산출한다.

LLM(v1.4.0 프롬프트)은 한글 키 24개(multi는 ";" 구분 문자열)로 출력하고, 서비스가
스키마(182878213 §A-1.1) 형태(camelCase 키 + multi는 JSON 배열)로 매핑한다. 스키마
ActivityTags 전체(36속성) 중 keyword1~3 등은 별도 모듈 산출이라 여기 24개에 포함되지 않는다.
설계 §6 '스키마 우선' — 프롬프트는 byte-exact 유지하고 변환만 코드에서 결정적으로 한다.
"""

import json

from utils.model import ANTHROPIC_MODEL, anthropic_async
from utils.record_prompt.tagging_prompt import (
    TAGGING_SYSTEM_PROMPT,
    TAGGING_PROMPT_VERSION,
)

# 프롬프트 한글 키 → 스키마 camelCase 키 (출처: 스키마 182878213 §A-1.1 주석)
_KO2CAMEL = {
    "활동구분": "activityType",
    "활동종류": "activityKind",
    "학업태도": "academicAttitude",
    "공동체역량": "communityCompetency",
    "교과연결": "subjectConnection",
    "연결교과목": "connectedSubject",
    "탐구방법": "inquiryMethod",
    "탐구깊이": "inquiryDepth",
    "활동연계": "activityLinkage",
    "활동연계_내용": "activityLinkageContent",
    "학술용어": "academicTerm",
    "학술용어내용": "academicTermContent",
    "결과물유형": "outputType",
    "독서연결": "readingConnection",
    "독서연결방식": "readingConnectionMethod",
    "책제목": "bookTitle",
    "진학학과연결": "majorConnection",
    "역할언급": "roleMention",
    "역할종류": "roleKind",
    "협력": "collaboration",
    "협력규모": "collaborationScale",
    "갈등조정기록": "conflictResolution",
    "자기성찰기록": "selfReflection",
    "계열": "track",
}

# 스키마에서 JSON 배열인 키(camelCase). 프롬프트는 ";" 구분 문자열로 주므로 split.
_MULTI = {
    "track",
    "academicAttitude",
    "communityCompetency",
    "inquiryMethod",
    "outputType",
    "readingConnectionMethod",
    "bookTitle",
    "collaborationScale",
}

# LLM 출력 구조 강제 — 한글 키 24개, 전부 문자열.
_TAGS_SCHEMA = {
    "type": "object",
    "properties": {ko: {"type": "string"} for ko in _KO2CAMEL},
    "required": list(_KO2CAMEL),
    "additionalProperties": False,
}


def _to_schema_tags(ko_tags: dict) -> dict:
    tags: dict = {}
    for ko, camel in _KO2CAMEL.items():
        value = ko_tags[ko]
        if camel in _MULTI:
            tags[camel] = [v.strip() for v in value.replace("；", ";").split(";") if v.strip()]
        else:
            tags[camel] = value
    return tags


async def extract_tags(activity: str, target_major: str | None) -> dict:
    user_message = f"활동: {activity}\n진학학과: {target_major or ''}"

    message = await anthropic_async.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2048,
        temperature=0,
        # 정적 system 프롬프트(~18KB) → prompt caching (활동마다 동일 프롬프트 재사용)
        system=[{"type": "text", "text": TAGGING_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": _TAGS_SCHEMA}},
        messages=[{"role": "user", "content": user_message}],
    )
    ko_tags = json.loads(message.content[0].text)

    return {
        "tags": _to_schema_tags(ko_tags),
        "prompt_version": TAGGING_PROMPT_VERSION,
    }
