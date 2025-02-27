from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List, Sequence
import operator
from typing import Annotated, Sequence
from langchain_core.messages import (
    BaseMessage,
)
from utils.model import anthropic, perple, perplexity_model, gpt4o
from services.difficulty_service_distil2.proto_researcher import protoResearcher, protoResearchDataset, protoResearchCollector



class ProtoResearchState(TypedDict):
    major: str
    keyword: str
    topic: str
    n_proto_research: int
    search_keywords: list
    phase: int
    information: Annotated[Sequence[BaseMessage], operator.add]
    additional_info: str
    charge: int

def call_proto_researcher_graph(parent_state):
    major = parent_state['major']
    keyword = parent_state['keyword']
    topic = parent_state['topic']
    n_research = parent_state['n_proto_research']
    search_keywords = parent_state['result_inspect']
    graph = StateGraph(ProtoResearchState)
    graph.add_node('protoResearchDataset', protoResearchDataset)
    graph.add_node('protoResearchCollector', protoResearchCollector)
    graph.set_entry_point('protoResearchDataset')
    for proto_n in range(n_research):
        def create_research_node(proto_n): 
            # 래퍼 함수: 기존 상태를 받아서 새로운 상태를 추가
            def wrapped_researcher(state):
                # 기존 state를 그대로 유지하면서 research_number 값을 추가
                state["phase"] = proto_n
                return protoResearcher(state)
            
            return wrapped_researcher


        graph.add_node('protoKeywordResearcher' + str(proto_n), create_research_node(proto_n))
        graph.add_edge('protoResearchDataset', 'protoKeywordResearcher'+str(proto_n))
        graph.add_edge('protoKeywordResearcher'+str(proto_n), 'protoResearchCollector')
    graph.add_edge('protoResearchCollector', END)
    graph_app = graph.compile()

    result = graph_app.invoke({'major':major, 'keyword':keyword, 'topic':topic, 'search_keywords': search_keywords})
    return {'information': result['additional_info'] }

def routing_branch_node(state):
    """
    분기 처리용 임의 노드
    """