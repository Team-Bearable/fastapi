import sys
import types

# import 루트(저장소 루트)는 pytest.ini 의 `pythonpath = .` 가 잡아준다 → 테스트는 `app.*`
# 정식 패키지 경로로 import 한다.

# app.worker.handlers.seteuk 가 import 하는 LLM 서비스 모듈을 스텁으로 대체한다.
# 실제 LLM 호출/langchain 클라이언트 구성 없이 워커 "배관"만 검증하기 위함이며,
# 개별 테스트는 monkeypatch 로 seteuk.recommend_topics / seteuk.run 을 원하는 값으로 바꾼다.
# sys.modules 키는 핸들러의 import 경로(app.services...)와 정확히 일치해야 스텁이 먹힌다.
_stub = types.ModuleType("app.services.difficulty_service_distil2.seteuk_topic")
_stub.recommend_topics = lambda *a, **k: []
sys.modules["app.services.difficulty_service_distil2.seteuk_topic"] = _stub

_stub_graph = types.ModuleType("app.services.difficulty_service_distil2.difficulty_graph")
_stub_graph.run = lambda *a, **k: {}
sys.modules["app.services.difficulty_service_distil2.difficulty_graph"] = _stub_graph
