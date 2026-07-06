"""키워드추출·제출물분석 핸들러 순수 로직 테스트 — LLM 서비스는 monkeypatch 로 대체."""

import pytest

from worker import dispatch
from worker.errors import InvalidPayload
from worker.handlers import keyword, submission


def test_keyword_info_assembly_and_shaping(monkeypatch):
    captured = {}

    def fake(info, introduction, body, conclusion):
        captured.update(info=info, introduction=introduction, body=body, conclusion=conclusion)
        return [{"keyword": "k1", "raw_weight": 7.2}]

    monkeypatch.setattr(keyword, "extract_keywords", fake)
    out = keyword.handle_keyword_extraction({
        "major": "물리학", "subject": "물리", "subjectDetail": "역학",
        "guideline": {"introduction": "서론", "body": "본론", "conclusion": "결론"},
    })

    assert captured["info"] == "물리학 - 물리 - 역학"       # major - subject - subjectDetail
    assert (captured["introduction"], captured["body"], captured["conclusion"]) == ("서론", "본론", "결론")
    assert out == {"keywords": [{"keyword": "k1", "raw_weight": 7.2}]}


def test_keyword_info_skips_missing_parts(monkeypatch):
    captured = {}
    monkeypatch.setattr(keyword, "extract_keywords",
                        lambda info, **k: captured.update(info=info) or [])
    keyword.handle_keyword_extraction({
        "subject": "물리",  # major·subjectDetail 없음
        "guideline": {"introduction": "i", "body": "b", "conclusion": "c"},
    })
    assert captured["info"] == "물리"                       # 빈 파트는 건너뜀


def test_keyword_missing_guideline_raises():
    with pytest.raises(InvalidPayload):
        keyword.handle_keyword_extraction({"major": "x"})


def test_keyword_missing_guideline_subfield_raises():
    with pytest.raises(InvalidPayload):
        keyword.handle_keyword_extraction({"guideline": {"introduction": "i", "body": "b"}})


async def test_submission_param_mapping_and_passthrough(monkeypatch):
    captured = {}

    async def fake(presigned_url, topic, master_category, sub_category, department, major):
        captured.update(presigned_url=presigned_url, topic=topic, master_category=master_category,
                        sub_category=sub_category, department=department, major=major)
        return {"summary": "요약", "review": "총평"}

    monkeypatch.setattr(submission, "analyze_report", fake)
    out = await submission.handle_submission_analysis({
        "presignedUrl": "https://s3/x", "topic": "T", "masterCategory": "M",
        "subCategory": "S", "department": "D", "major": "J",
    })

    assert captured == {"presigned_url": "https://s3/x", "topic": "T", "master_category": "M",
                        "sub_category": "S", "department": "D", "major": "J"}
    assert out == {"summary": "요약", "review": "총평"}


async def test_submission_optional_fields_default_none(monkeypatch):
    captured = {}

    async def fake(presigned_url, **kw):
        captured.update(presigned_url=presigned_url, **kw)
        return {"summary": "", "review": ""}

    monkeypatch.setattr(submission, "analyze_report", fake)
    await submission.handle_submission_analysis({"presignedUrl": "https://s3/x"})
    assert captured["topic"] is None and captured["major"] is None  # 선택 필드 미지정 → None


async def test_submission_missing_url_raises():
    with pytest.raises(InvalidPayload):
        await submission.handle_submission_analysis({"topic": "T"})


async def test_dispatch_routes_new_jobtypes(monkeypatch):
    monkeypatch.setattr(keyword, "extract_keywords", lambda **k: [])

    async def fake_analyze(presigned_url, **kw):
        return {"summary": "", "review": ""}

    monkeypatch.setattr(submission, "analyze_report", fake_analyze)

    assert await dispatch.dispatch("KEYWORD_EXTRACTION", {
        "guideline": {"introduction": "i", "body": "b", "conclusion": "c"},
    }) == {"keywords": []}
    assert await dispatch.dispatch("SUBMISSION_ANALYSIS", {"presignedUrl": "u"}) == {"summary": "", "review": ""}
