"""세특 핸들러 순수 로직 테스트 — LLM(recommend_topics/run)은 monkeypatch 로 대체."""

import pytest

from worker import dispatch
from worker.errors import InvalidPayload, UnsupportedJobType
from worker.handlers import seteuk


def test_topic_split_and_keyword(monkeypatch):
    captured = {}

    def fake(major, keyword, depth):
        captured["depth"] = depth
        return ["주제1::팁1::검색1", "주제2::팁2::검색2"]

    monkeypatch.setattr(seteuk, "recommend_topics", fake)
    out = seteuk.handle_topic_recommend(
        {"major": "재료공학", "keyword": "삼각함수", "seteukDepth": "BASIC"}
    )

    assert captured["depth"] == "Basic"  # BASIC → Basic 매핑
    # topic/tip 은 "::" 분할, keyword 는 검색어(검색1)가 아니라 입력 키워드(삼각함수)
    assert out == {"topics": [
        {"topic": "주제1", "tip": "팁1", "keyword": "삼각함수"},
        {"topic": "주제2", "tip": "팁2", "keyword": "삼각함수"},
    ]}


def test_topic_depth_mapping(monkeypatch):
    seen = []
    monkeypatch.setattr(seteuk, "recommend_topics", lambda m, k, d: seen.append(d) or [])
    for enum in ("BASIC", "INTERMEDIATE", "ADVANCED"):
        seteuk.handle_topic_recommend({"major": "x", "keyword": "k", "seteukDepth": enum})
    assert seen == ["Basic", "Applied", "Advanced"]


def test_topic_malformed_line(monkeypatch):
    # "::" 가 없는 줄도 topic 만 채우고 tip 은 빈값(방어).
    monkeypatch.setattr(seteuk, "recommend_topics", lambda *a, **k: ["주제만"])
    out = seteuk.handle_topic_recommend({"major": "x", "keyword": "k", "seteukDepth": "BASIC"})
    assert out == {"topics": [{"topic": "주제만", "tip": "", "keyword": "k"}]}


def test_unknown_depth_raises(monkeypatch):
    monkeypatch.setattr(seteuk, "recommend_topics", lambda *a, **k: [])
    with pytest.raises(InvalidPayload):
        seteuk.handle_topic_recommend({"major": "x", "keyword": "k", "seteukDepth": "HARD"})


def test_missing_field_raises():
    # 필수 필드(major) 누락 → InvalidPayload
    with pytest.raises(InvalidPayload):
        seteuk.handle_topic_recommend({"keyword": "k", "seteukDepth": "BASIC"})


def test_guideline_shaping(monkeypatch):
    captured = {}

    def fake_run(major, keyword, topic, depth):
        captured.update(keyword=keyword, depth=depth)
        return {
            "proto": {"introduction": "p"},
            "introduction": "서론", "body": "본론", "conclusion": "결론",
            "reference_news": [{"title": "t", "institute": "i", "url": "u", "date": None}],
        }

    monkeypatch.setattr(seteuk, "run", fake_run)
    out = seteuk.handle_guideline_generate(
        {"major": "물리", "keywords": ["미분"], "topic": "T", "seteukDepth": "INTERMEDIATE"}
    )

    assert captured["keyword"] == "미분"          # keywords[0] 사용
    assert captured["depth"] == "Applied"          # INTERMEDIATE → Applied
    assert set(out) == {"introduction", "body", "conclusion", "referenceNews"}
    assert "proto" not in out                       # proto 드롭
    assert out["referenceNews"] == [{"title": "t", "institute": "i", "url": "u", "date": None}]


def test_guideline_empty_keywords(monkeypatch):
    captured = {}
    monkeypatch.setattr(seteuk, "run",
                        lambda m, k, t, d: captured.update(keyword=k) or
                        {"introduction": "", "body": "", "conclusion": "", "reference_news": []})
    out = seteuk.handle_guideline_generate(
        {"major": "x", "keywords": [], "topic": "T", "seteukDepth": "BASIC"}
    )
    assert captured["keyword"] == ""                # 빈 keywords → ""
    assert out["referenceNews"] == []


async def test_dispatch_routes_and_rejects(monkeypatch):
    monkeypatch.setattr(seteuk, "recommend_topics", lambda *a, **k: [])
    assert await dispatch.dispatch(
        "SETEUK_TOPIC_RECOMMEND", {"major": "x", "keyword": "k", "seteukDepth": "BASIC"}
    ) == {"topics": []}
    with pytest.raises(UnsupportedJobType):
        await dispatch.dispatch("NOPE", {})
