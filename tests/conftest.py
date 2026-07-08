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
