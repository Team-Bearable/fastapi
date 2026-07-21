"""세특 플러스 생성 (LangGraph: topic → research → 병렬 refine).

흐름:
    plus_topic(Claude)  →  plus_research(perplexity)  →  refine_intro/body/conclusion(gpt4o, 병렬)
    - topic/tip 생성        실제 사례+출처 URL 검색        각 섹션을 주제·사례로 상세 작성

- topic/tip 도 AI 가 생성한다(베이직은 topic 을 입력받음).
- 리서치는 베이직의 검증된 perplexity 노드를 재사용(실제 사례 + citation URL). 결과는 서론/본론/결론
  '본문 안'에 자연스럽게 녹인다(별도 필드로 나가지 않음).
- proto(초안) 단계는 두지 않는다: 품질은 refine 프롬프트 + few-shot 예시에서 나오고, proto 는
  시간만 늘려 실익이 없었다.

결과 계약: {topic, tip, introduction, body, conclusion}
"""

import json
import re
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from app.utils.model import anthropic, gpt4o
from app.utils.logger import get_logger
from app.utils.seteuk_plus_prompt import (
    seteukPlusTopic,
    seteukPlusIntroduction, seteukPlusBody, seteukPlusConclusion,
)
# 리서치(관련 사례 + 출처 URL)는 베이직의 검증된 perplexity 노드를 그대로 재사용한다.
# perplexity 로 실제 사례를 찾고 gpt4o(material_organizer)로 정리 + citation URL 첨부까지 해준다.
from app.services.difficulty_service_distil2.case_researcher import perplexity as _basic_perplexity

log = get_logger("seteuk_plus")


class PlusState(TypedDict, total=False):
    # 입력
    department: str
    major: str
    subject: str
    keyword: str
    seteuk_depth: str
    # 단계별 산출물
    topic: str
    tip: str
    case_result: str     # 리서치 결과: <<<관련 사례>>>/<<<응용 탐구>>> + 출처 URL (없으면 "")
    introduction: str
    body: str
    conclusion: str


def _chain(prompt_obj, model, keys):
    """system/human 프롬프트 객체로 LangChain 체인을 만든다."""
    template = ChatPromptTemplate.from_messages(
        [("system", prompt_obj.system), ("user", prompt_obj.human)]
    )
    passthrough = {k: RunnablePassthrough() for k in keys}
    return passthrough | template | model | StrOutputParser()


def _parse_topic(raw: str) -> dict:
    """모델 응답에서 topic/tip 을 뽑는다. 형식이 흔들려도 견디게 다단계로 방어.

    우선순위: 구분자(<<<TOPIC>>>/<<<TIP>>>) → JSON → 첫 줄/나머지 최소 복구.
    """
    text = re.sub(r"```[a-zA-Z]*", "", raw).strip()  # 코드블록 펜스 제거

    m = re.search(r"<<<TOPIC>>>(.*?)<<<TIP>>>(.*)", text, re.DOTALL)
    if m:
        return {"topic": m.group(1).strip(), "tip": m.group(2).strip()}

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return {"topic": data.get("topic", ""), "tip": data.get("tip", "")}
        except json.JSONDecodeError:
            pass

    first, _, rest = text.partition("\n")
    return {"topic": first.strip(), "tip": rest.strip()}


# ── LangGraph 노드 ──────────────────────────────────────────────────────────
def plus_topic(state: PlusState) -> dict:
    """① topic + tip 생성 (창의성 필요 → anthropic). seteuk_depth 는 영문 난이도."""
    raw = _chain(
        seteukPlusTopic(), anthropic,
        ["department", "major", "subject", "keyword", "seteuk_depth"],
    ).invoke({
        "department": state["department"], "major": state["major"],
        "subject": state["subject"], "keyword": state["keyword"],
        "seteuk_depth": state["seteuk_depth"],
    })
    tp = _parse_topic(raw)
    log.info("plus_topic 완료 topic=%.40s", tp["topic"])
    return {"topic": tp["topic"], "tip": tp["tip"]}


def plus_research(state: PlusState) -> dict:
    """② 실제 사례 리서치 (베이직 perplexity 재사용). refine 이 본문에 사례를 녹여야 하므로
    refine 보다 먼저 끝나야 한다. 실패해도 사례 없이 진행한다(생성 자체를 막지 않는다)."""
    try:
        out = _basic_perplexity(state)  # state 에 major/topic 있음
        case = (out or {}).get("case_result", "") or ""
        log.info("plus_research 완료 len=%d", len(case))
        return {"case_result": case}
    except Exception as e:
        log.warning("plus_research 실패 — 사례 없이 진행: %s", e)
        return {"case_result": ""}


def _refine(state: PlusState, prompt_obj) -> str:
    """주제(+리서치 사례)로 각 섹션 최종본 생성 (gpt4o).

    reference(리서치로 찾은 실제 사례+URL)를 함께 넘겨, 프롬프트가 이를 섹션 본문 흐름에
    자연스럽게 녹여 인용하게 한다(서론/본론/결론 밖으로 새지 않음).
    """
    return _chain(
        prompt_obj, gpt4o,
        ["major", "subject", "seteuk_depth", "topic", "reference"],
    ).invoke({
        "major": state["major"], "subject": state["subject"],
        "seteuk_depth": state["seteuk_depth"], "topic": state["topic"],
        "reference": state.get("case_result", "") or "(참고 자료 없음)",
    })


def refine_intro(state: PlusState) -> dict:
    result = _refine(state, seteukPlusIntroduction())
    log.info("refine_intro 완료 len=%d", len(result))
    return {"introduction": result}


def refine_body(state: PlusState) -> dict:
    result = _refine(state, seteukPlusBody())
    log.info("refine_body 완료 len=%d", len(result))
    return {"body": result}


def refine_conclusion(state: PlusState) -> dict:
    result = _refine(state, seteukPlusConclusion())
    log.info("refine_conclusion 완료 len=%d", len(result))
    return {"conclusion": result}


def _build_graph():
    """topic → research → (서론/본론/결론 병렬 refine) → END."""
    graph = StateGraph(PlusState)
    graph.add_node("plus_topic", plus_topic)
    graph.add_node("plus_research", plus_research)
    graph.add_node("refine_intro", refine_intro)
    graph.add_node("refine_body", refine_body)
    graph.add_node("refine_conclusion", refine_conclusion)

    graph.set_entry_point("plus_topic")
    # 사례를 refine 이 본문에 녹여야 하므로 research 가 refine 보다 먼저 끝나야 한다 → 순차.
    graph.add_edge("plus_topic", "plus_research")
    # research 이후 세 섹션을 fan-out → 같은 superstep 에서 병렬 실행됨
    graph.add_edge("plus_research", "refine_intro")
    graph.add_edge("plus_research", "refine_body")
    graph.add_edge("plus_research", "refine_conclusion")
    graph.add_edge("refine_intro", END)
    graph.add_edge("refine_body", END)
    graph.add_edge("refine_conclusion", END)
    return graph.compile()


# 그래프는 stateless 하므로 모듈 로드 시 한 번만 컴파일해 재사용한다.
_PLUS_APP = _build_graph()


def run_plus(department, major, subject, keyword, seteuk_depth) -> dict:
    """seteuk_depth 는 프롬프트가 받는 영문 난이도(Basic/Applied/Advanced)다.

    핸들러 계약 유지: 입력/출력 시그니처는 기존과 동일.
    """
    result = _PLUS_APP.invoke({
        "department": department or "",
        "major": major,
        "subject": subject or "",
        "keyword": keyword,
        "seteuk_depth": seteuk_depth,
    })
    return {
        "topic": result["topic"],
        "tip": result["tip"],
        "introduction": result["introduction"],
        "body": result["body"],
        "conclusion": result["conclusion"],
    }
