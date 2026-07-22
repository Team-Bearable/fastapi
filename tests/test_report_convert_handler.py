"""활동 리포트 변환 핸들러 순수 로직 테스트 — LLM 서비스는 monkeypatch 로 대체."""

import pytest

from app.worker import dispatch
from app.worker.errors import InvalidPayload, JobFailed
from app.worker.handlers import report_convert
from app.services.report_conversion import ContentPolicyError, ConversionError

_MINIMAL = {"reportTitle": "제목", "content": "원문", "section": "SUBJECT", "grade": 2}


async def test_param_mapping_camel_to_snake(monkeypatch):
    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return {"activityContent": "정리된 활동", "promptVersion": "convert-v1"}

    monkeypatch.setattr(report_convert, "convert_report", fake)
    out = await report_convert.handle_report_convert({
        "reportTitle": "T", "content": "C", "section": "SUBJECT", "grade": 3,
        "subSection": None, "semester": 1, "courseName": "확률과 통계",
        "academicFieldName": "경우의 수", "keywords": ["조건부확률"], "desiredField": "데이터과학",
    })

    assert captured == {
        "report_title": "T", "content": "C", "section": "SUBJECT", "grade": 3,
        "sub_section": None, "semester": 1, "course_name": "확률과 통계",
        "academic_field_name": "경우의 수", "keywords": ["조건부확률"], "desired_field": "데이터과학",
    }
    assert out == {"activityContent": "정리된 활동", "promptVersion": "convert-v1"}


async def test_optional_fields_default_none(monkeypatch):
    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return {"activityContent": "x", "promptVersion": "convert-v1"}

    monkeypatch.setattr(report_convert, "convert_report", fake)
    await report_convert.handle_report_convert(dict(_MINIMAL))
    # 선택 필드 미지정 → None (교과외/과목 없는 리포트)
    assert captured["sub_section"] is None
    assert captured["semester"] is None
    assert captured["course_name"] is None
    assert captured["academic_field_name"] is None
    assert captured["keywords"] is None
    assert captured["desired_field"] is None


@pytest.mark.parametrize("missing", ["reportTitle", "content", "section", "grade"])
async def test_missing_required_raises(missing):
    payload = dict(_MINIMAL)
    del payload[missing]
    with pytest.raises(InvalidPayload):
        await report_convert.handle_report_convert(payload)


async def test_invalid_section_raises():
    with pytest.raises(InvalidPayload):
        await report_convert.handle_report_convert({**_MINIMAL, "section": "NOPE"})


async def test_invalid_subsection_raises():
    with pytest.raises(InvalidPayload):
        await report_convert.handle_report_convert({**_MINIMAL, "subSection": "NOPE"})


async def test_valid_subsection_passes(monkeypatch):
    monkeypatch.setattr(report_convert, "convert_report",
                        lambda **k: _async_return({"activityContent": "x", "promptVersion": "convert-v1"}))
    out = await report_convert.handle_report_convert(
        {**_MINIMAL, "section": "EXTRACURRICULAR", "subSection": "CLUB"}
    )
    assert out["activityContent"] == "x"


async def test_content_policy_maps_to_jobfailed(monkeypatch):
    async def fake(**kw):
        raise ContentPolicyError("blocked")

    monkeypatch.setattr(report_convert, "convert_report", fake)
    with pytest.raises(JobFailed) as ei:
        await report_convert.handle_report_convert(dict(_MINIMAL))
    assert ei.value.code == "LLM_CONTENT_POLICY"


async def test_conversion_error_maps_to_invalid_input(monkeypatch):
    async def fake(**kw):
        raise ConversionError("empty")

    monkeypatch.setattr(report_convert, "convert_report", fake)
    with pytest.raises(JobFailed) as ei:
        await report_convert.handle_report_convert(dict(_MINIMAL))
    assert ei.value.code == "LLM_INVALID_INPUT"


async def test_dispatch_routes_report_convert(monkeypatch):
    async def fake(**kw):
        return {"activityContent": "정리", "promptVersion": "convert-v1"}

    monkeypatch.setattr(report_convert, "convert_report", fake)
    out = await dispatch.dispatch("REPORT_CONVERT", dict(_MINIMAL))
    assert out == {"activityContent": "정리", "promptVersion": "convert-v1"}


async def _async_return(value):
    return value
