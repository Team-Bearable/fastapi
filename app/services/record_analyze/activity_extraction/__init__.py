"""활동추출 — source_record.content를 LLM으로 활동 단위(verbatim) 분할.

섹션별 프롬프트 분기: 창체·세특(ACTIVITY) / 행특(BEHAVIOR). 출력은 원문 슬라이스라
이어붙이면 입력과 동일해야 한다. LLM이 이 계약을 어기면 손실 0으로 폴백(verbatim_ok=False).
"""

import json

from utils.model import ANTHROPIC_MODEL, anthropic_async
from utils.record_prompt.changche_seteuk_prompt import (
    CHANGCHE_SETEUK_SYSTEM_PROMPT,
    CHANGCHE_SETEUK_PROMPT_VERSION,
)
from utils.record_prompt.haengtuk_prompt import (
    HAENGTEUK_SYSTEM_PROMPT,
    HAENGTEUK_PROMPT_VERSION,
)

_ACTIVITIES_SCHEMA = {
    "type": "object",
    "properties": {"activities": {"type": "array", "items": {"type": "string"}}},
    "required": ["activities"],
    "additionalProperties": False,
}


def _prompt_for(section: str) -> tuple[str, str]:
    if section == "HAENGTEUK":
        return HAENGTEUK_SYSTEM_PROMPT, HAENGTEUK_PROMPT_VERSION
    return CHANGCHE_SETEUK_SYSTEM_PROMPT, CHANGCHE_SETEUK_PROMPT_VERSION


async def extract_activities(content: str, section: str) -> dict:
    system_prompt, prompt_version = _prompt_for(section)

    message = await anthropic_async.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0,
        # 정적 system 프롬프트 → prompt caching (레코드마다 동일 프롬프트 재사용)
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": _ACTIVITIES_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    activities = json.loads(message.content[0].text)["activities"]

    # 이어붙이면 원문과 동일해야 verbatim 보장. 어기면(누락/교정/요약) 손실 0으로 폴백.
    verbatim_ok = "".join(activities) == content
    if not verbatim_ok:
        activities = [content]

    return {
        "activities": activities,
        "prompt_version": prompt_version,
        "verbatim_ok": verbatim_ok,
    }
