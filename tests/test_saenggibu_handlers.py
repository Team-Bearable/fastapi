"""생기부 핸들러 로직 테스트 — OCR/LLM 서비스는 conftest 스텁 + monkeypatch."""

import pytest

from worker.errors import InvalidPayload, JobFailed
from worker.handlers import saenggibu
from worker.handlers.saenggibu import (
    MissingSectionError,
    OcrError,
    UnsupportedRecordFormatError,
)


def test_record_extract_renames_page_range(monkeypatch):
    monkeypatch.setattr(saenggibu, "extract_source_records", lambda url: [
        {"section": "SETEUK", "grade": 2, "meta": {"subject": "수학"},
         "content": "본문", "source_page_range": [3, 4]},
    ])
    out = saenggibu.handle_record_extract({"pdfFileUrl": "https://x/y.pdf"})
    rec = out["records"][0]
    assert rec["sourcePageRange"] == [3, 4]          # snake → camel
    assert "source_page_range" not in rec
    assert rec["section"] == "SETEUK" and rec["content"] == "본문"


@pytest.mark.parametrize("exc,code", [
    (UnsupportedRecordFormatError, "UNSUPPORTED_RECORD_FORMAT"),
    (MissingSectionError, "MISSING_SECTION"),
    (OcrError, "OCR_FAILED"),
    (RuntimeError, "RECORD_EXTRACT_FAILED"),  # 다운로드 등 그 외 실패 → 전용 코드(LLM_FAILED 아님)
])
def test_record_extract_error_mapping(monkeypatch, exc, code):
    def boom(url):
        raise exc("nope")
    monkeypatch.setattr(saenggibu, "extract_source_records", boom)
    with pytest.raises(JobFailed) as ei:
        saenggibu.handle_record_extract({"pdfFileUrl": "u"})
    assert ei.value.code == code


def test_record_extract_missing_field():
    with pytest.raises(InvalidPayload):
        saenggibu.handle_record_extract({})  # pdfFileUrl 없음


async def test_activity_extract_source_span(monkeypatch):
    async def fake(content, section):
        return {"activities": ["가나", "다라마", "바"], "verbatim_ok": True}
    monkeypatch.setattr(saenggibu, "extract_activities", fake)
    content = "가나다라마바"
    out = await saenggibu.handle_activity_extract({"content": content, "section": "SETEUK"})
    spans = [a["sourceSpan"] for a in out["activities"]]
    assert spans == [{"start": 0, "end": 2}, {"start": 2, "end": 5}, {"start": 5, "end": 6}]
    # 오프셋으로 원문 슬라이스가 정확히 복원돼야 한다
    assert [content[s["start"]:s["end"]] for s in spans] == ["가나", "다라마", "바"]


async def test_activity_extract_fallback_single(monkeypatch):
    # verbatim 저하 → [content] 1활동. SUCCESS 로 span 하나.
    async def fake(content, section):
        return {"activities": [content], "verbatim_ok": False}
    monkeypatch.setattr(saenggibu, "extract_activities", fake)
    out = await saenggibu.handle_activity_extract({"content": "전체본문", "section": "HAENGTEUK"})
    assert out["activities"] == [{"sourceSpan": {"start": 0, "end": 4}}]


async def test_tagging_passthrough(monkeypatch):
    captured = {}
    async def fake(activity, target_major):
        captured.update(activity=activity, major=target_major)
        return {"tags": {"track": ["의학"]}, "prompt_version": "1.4"}
    monkeypatch.setattr(saenggibu, "extract_tags", fake)
    out = await saenggibu.handle_tagging(
        {"activityId": "a1", "activityText": "활동내용", "targetMajor": "의예과"}
    )
    assert captured == {"activity": "활동내용", "major": "의예과"}
    assert out == {"tags": {"track": ["의학"]}}       # tags 만, prompt_version 제외


async def test_tagging_optional_major(monkeypatch):
    async def fake(activity, target_major):
        assert target_major is None                    # 없으면 None
        return {"tags": {}}
    monkeypatch.setattr(saenggibu, "extract_tags", fake)
    await saenggibu.handle_tagging({"activityText": "x"})
