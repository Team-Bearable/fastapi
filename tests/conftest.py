import os
import sys
import types

# app/ 을 sys.path 루트로 (worker.*, services.*, utils.* 절대 import — 앱 실행과 동일 규약).
APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
sys.path.insert(0, APP)

# worker.handlers.seteuk 가 import 하는 LLM 서비스 모듈을 스텁으로 대체한다.
# 실제 LLM 호출/langchain 클라이언트 구성 없이 워커 "배관"만 검증하기 위함이며,
# 개별 테스트는 monkeypatch 로 seteuk.recommend_topics / seteuk.run 을 원하는 값으로 바꾼다.
_stub = types.ModuleType("services.difficulty_service_distil2.seteuk_topic")
_stub.recommend_topics = lambda *a, **k: []
sys.modules["services.difficulty_service_distil2.seteuk_topic"] = _stub

_stub_graph = types.ModuleType("services.difficulty_service_distil2.difficulty_graph")
_stub_graph.run = lambda *a, **k: {}
sys.modules["services.difficulty_service_distil2.difficulty_graph"] = _stub_graph

# 생기부(record_analyze) 서비스도 스텁 — PyMuPDF/Vision OCR/langchain 없이 배관만 검증.
_se = types.ModuleType("services.record_analyze.source_extraction")
_se.extract_source_records = lambda url: []
sys.modules["services.record_analyze.source_extraction"] = _se

_exc = types.ModuleType("services.record_analyze.source_extraction.exceptions")
for _name in ("UnsupportedRecordFormatError", "MissingSectionError", "OcrError"):
    setattr(_exc, _name, type(_name, (Exception,), {}))
sys.modules["services.record_analyze.source_extraction.exceptions"] = _exc

async def _stub_extract_activities(content, section):
    return {"activities": [content], "verbatim_ok": False}
_ae = types.ModuleType("services.record_analyze.activity_extraction")
_ae.extract_activities = _stub_extract_activities
sys.modules["services.record_analyze.activity_extraction"] = _ae

async def _stub_extract_tags(activity, target_major):
    return {"tags": {}}
_tg = types.ModuleType("services.record_analyze.tagging")
_tg.extract_tags = _stub_extract_tags
sys.modules["services.record_analyze.tagging"] = _tg
