"""세특 jobType 별 처리기 — 요청 payload(dict)를 받아 결과(dict)를 돌려준다.

입력/출력 모양은 myfolio(Java)와 맞춘 것이다:
- SETEUK_TOPIC_RECOMMEND: {major, keyword, seteukDepth} → {topics:[{topic,tip,keyword}]}
- SETEUK_GUIDELINE_GENERATE: {major, keywords[], topic, seteukDepth}
  → {introduction, body, conclusion, referenceNews[]}
- SETEUK_PLUS_GENERATE: {department, major, subject, plusKeyword, seteukDepth}
  → {topic, tip, introduction, body, conclusion}   (topic/tip 도 AI 생성, 사례 없음)
"""

from app.services.difficulty_service_distil2.seteuk_topic import recommend_topics
from app.services.difficulty_service_distil2.difficulty_graph import run
from app.services.difficulty_service_distil2.seteuk_plus import run_plus
from app.worker.errors import InvalidPayload

# Java 가 보내는 난이도 값을 프롬프트가 쓰는 표현으로 바꾼다.
_DEPTH = {"BASIC": "Basic", "INTERMEDIATE": "Applied", "ADVANCED": "Advanced"}


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


def _depth(value: str) -> str:
    try:
        return _DEPTH[value]
    except KeyError:
        raise InvalidPayload(f"unsupported seteukDepth: {value!r}")


def handle_topic_recommend(payload: dict) -> dict:
    keyword = _require(payload, "keyword")
    lines = recommend_topics(
        _require(payload, "major"), keyword, _depth(_require(payload, "seteukDepth"))
    )

    topics = []
    for line in lines:
        parts = line.split("::")
        topics.append({
            "topic": parts[0].strip() if len(parts) > 0 else "",
            "tip": parts[1].strip() if len(parts) > 1 else "",
            # 검색어가 아니라 입력 키워드를 넣는다 — Java 가 같은 키워드의 기존 결과를 이걸로 찾아
            # 교체하므로(재시도 시 중복 방지), 여기가 입력 키워드와 같아야 한다.
            "keyword": keyword,
        })
    return {"topics": topics}


def handle_guideline_generate(payload: dict) -> dict:
    keywords = payload.get("keywords") or []
    keyword = keywords[0] if keywords else ""
    result = run(
        _require(payload, "major"), keyword,
        _require(payload, "topic"), _depth(_require(payload, "seteukDepth")),
    )
    return {
        "introduction": result.get("introduction"),
        "body": result.get("body"),
        "conclusion": result.get("conclusion"),
        "referenceNews": result.get("reference_news") or [],
    }


def handle_plus_generate(payload: dict) -> dict:
    # 분야/전공/과목 스냅샷 + 유저 자유 키워드(plusKeyword). 스냅샷은 없을 수 있어 관대하게.
    return run_plus(
        payload.get("department") or "",
        _require(payload, "major"),
        payload.get("subject") or "",
        _require(payload, "plusKeyword"),
        _depth(_require(payload, "seteukDepth")),
    )
