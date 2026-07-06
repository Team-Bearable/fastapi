"""키워드 추출 jobType 처리기 — 요청 payload(dict) → 결과(dict).

Java WordCloudAiAdapter 와 맞춘 입출력:
- KEYWORD_EXTRACTION: {major?, subject?, subjectDetail?, guideline{introduction,body,conclusion}}
  → {keywords:[{keyword, raw_weight}]}
"""

from services.keyword_extraction import extract_keywords
from worker.errors import InvalidPayload


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


def handle_keyword_extraction(payload: dict) -> dict:
    guideline = _require(payload, "guideline")
    info = " - ".join(
        v for v in (payload.get("major"), payload.get("subject"), payload.get("subjectDetail")) if v
    )
    keywords = extract_keywords(
        info=info,
        introduction=_require(guideline, "introduction"),
        body=_require(guideline, "body"),
        conclusion=_require(guideline, "conclusion"),
    )
    return {"keywords": keywords}
