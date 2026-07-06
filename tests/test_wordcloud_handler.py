"""워드클라우드 핸들러 테스트 — 이미지 생성/업로드는 monkeypatch 로 대체."""

from io import BytesIO

import pytest

from worker import dispatch
from worker.errors import InvalidPayload, JobFailed
from worker.handlers import wordcloud


def _patch_generate(monkeypatch, png=b"PNGDATA"):
    monkeypatch.setattr(wordcloud, "generate_word_cloud", lambda *a, **k: BytesIO(png))


def test_generates_and_uploads_to_presigned_url(monkeypatch):
    captured = {}
    _patch_generate(monkeypatch, png=b"PNGBYTES")

    def fake_put(url, data, headers, timeout):
        captured.update(url=url, data=data, headers=headers)
        return type("R", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr(wordcloud.requests, "put", fake_put)

    out = wordcloud.handle_word_cloud({
        "keywords": [{"keyword": "k", "raw_weight": 1.0}],
        "font": 0, "color": 0, "mask": 0, "uploadUrl": "https://s3/put",
    })

    assert out == {}                                   # 결과 본문 없음
    assert captured["url"] == "https://s3/put"
    assert captured["data"] == b"PNGBYTES"             # 생성된 PNG bytes 를 PUT
    assert captured["headers"]["Content-Type"] == "image/png"


def test_generate_args_forwarded(monkeypatch):
    captured = {}
    monkeypatch.setattr(wordcloud, "generate_word_cloud",
                        lambda keywords, font, color, mask: captured.update(
                            keywords=keywords, font=font, color=color, mask=mask) or BytesIO(b"x"))
    monkeypatch.setattr(wordcloud, "_upload_png", lambda url, data: None)

    wordcloud.handle_word_cloud({
        "keywords": [{"keyword": "k", "raw_weight": 2.0}],
        "font": 3, "color": 5, "mask": 1, "uploadUrl": "u",
    })
    assert captured == {"keywords": [{"keyword": "k", "raw_weight": 2.0}], "font": 3, "color": 5, "mask": 1}


@pytest.mark.parametrize("missing", ["keywords", "font", "color", "mask", "uploadUrl"])
def test_missing_field_raises_invalid_payload(missing):
    payload = {"keywords": [{"keyword": "k", "raw_weight": 1.0}],
               "font": 0, "color": 0, "mask": 0, "uploadUrl": "u"}
    del payload[missing]
    with pytest.raises(InvalidPayload):
        wordcloud.handle_word_cloud(payload)


def test_empty_keywords_is_invalid_payload_not_word_cloud_failed():
    # 빈 키워드는 입력 계약 위반(INVALID_PAYLOAD) — 처리실패(WORD_CLOUD_FAILED) 아님
    with pytest.raises(InvalidPayload):
        wordcloud.handle_word_cloud({
            "keywords": [], "font": 0, "color": 0, "mask": 0, "uploadUrl": "u",
        })


def test_upload_failure_wrapped_as_word_cloud_failed(monkeypatch):
    _patch_generate(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(wordcloud.requests, "put", boom)
    with pytest.raises(JobFailed) as ei:
        wordcloud.handle_word_cloud({
            "keywords": [{"keyword": "k", "raw_weight": 1.0}],
            "font": 0, "color": 0, "mask": 0, "uploadUrl": "u",
        })
    assert ei.value.code == "WORD_CLOUD_FAILED"        # LLM_FAILED fallback 아님


def test_generate_failure_wrapped_as_word_cloud_failed(monkeypatch):
    monkeypatch.setattr(wordcloud, "generate_word_cloud",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad mask")))
    with pytest.raises(JobFailed) as ei:
        wordcloud.handle_word_cloud({
            "keywords": [{"keyword": "k", "raw_weight": 1.0}],
            "font": 0, "color": 0, "mask": 99, "uploadUrl": "u",
        })
    assert ei.value.code == "WORD_CLOUD_FAILED"


async def test_dispatch_routes_word_cloud(monkeypatch):
    _patch_generate(monkeypatch)
    monkeypatch.setattr(wordcloud, "_upload_png", lambda url, data: None)
    out = await dispatch.dispatch("WORD_CLOUD", {
        "keywords": [{"keyword": "k", "raw_weight": 1.0}],
        "font": 0, "color": 0, "mask": 0, "uploadUrl": "u",
    })
    assert out == {}
