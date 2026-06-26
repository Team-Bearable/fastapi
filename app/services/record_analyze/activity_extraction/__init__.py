"""활동추출 — source_record.content를 LLM으로 활동 단위(verbatim) 분할.

섹션별 프롬프트 분기: 창체·세특 / 행특. 출력은 원문 슬라이스라 이어붙이면 입력과 동일해야 한다.
verbatim 불일치 중 '내용 누락성(severe)'은 비결정적 blip이라 재시도로 복구한다. 따옴표·공백
정규화 같은 cosmetic 차이는 체계적이라 재시도해도 같으므로 재시도하지 않는다. 끝내 못 맞추면
손실 0으로 통째 1활동 폴백(verbatim_ok=False).
"""

import json
from difflib import SequenceMatcher

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

# 원문 대비 유사도가 이 값 미만이면 '내용 누락성(severe)' → 재시도. 이상이면 cosmetic으로 본다.
_SEVERE_RATIO = 0.9
_MAX_RETRIES = 2


def _prompt_for(section: str) -> tuple[str, str]:
    if section == "HAENGTEUK":
        return HAENGTEUK_SYSTEM_PROMPT, HAENGTEUK_PROMPT_VERSION
    return CHANGCHE_SETEUK_SYSTEM_PROMPT, CHANGCHE_SETEUK_PROMPT_VERSION


async def _segment(content: str, system_prompt: str) -> list[str]:
    message = await anthropic_async.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=8192,
        temperature=0,
        # 정적 system 프롬프트 → prompt caching (레코드마다 동일 프롬프트 재사용)
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": _ACTIVITIES_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    return json.loads(message.content[0].text)["activities"]


async def extract_activities(content: str, section: str) -> dict:
    system_prompt, prompt_version = _prompt_for(section)

    for _ in range(_MAX_RETRIES + 1):
        activities = await _segment(content, system_prompt)
        if "".join(activities) == content:
            return {"activities": activities, "prompt_version": prompt_version, "verbatim_ok": True}
        # cosmetic(체계적) 차이면 재시도해도 같으므로 폴백. severe(누락성 blip)만 재시도.
        if SequenceMatcher(None, content, "".join(activities)).ratio() >= _SEVERE_RATIO:
            break

    return {"activities": [content], "prompt_version": prompt_version, "verbatim_ok": False}
