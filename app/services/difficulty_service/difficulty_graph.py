from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List, Sequence
import operator
from typing import Annotated, Sequence
from langchain_core.messages import (
    BaseMessage,
)
from services.difficulty_service.guidelines import seteuk_intro, seteuk_body, seteuk_conclusion
from services.difficulty_service.difficulty_subgraph import call_proto_researcher_graph, routing_branch_node
from services.difficulty_service.proto import protoGenerator, protoInspector, protoInspectorRouter
from services.difficulty_service.case_researcher import perplexity



class MainState(TypedDict):
    topic: str
    major: str
    keyword: str
    seteuk_depth: str
    proto: str
    introduction: str
    body: str
    conclusion: str
    n_proto_research: int
    information: str
    case_result: str
    reference_news: str
    messages: Annotated[Sequence[BaseMessage], operator.add]      # 진행 내역 저장


def GraphGenerate():
    graph = StateGraph(MainState)
    graph.add_node('protoGenerator', protoGenerator)
    graph.add_node('protoInspector', protoInspector)
    graph.add_node('call_proto_researcher_graph', call_proto_researcher_graph)
    graph.add_node('perplexity', perplexity)
    graph.add_node('seteuk_body', seteuk_body)
    graph.add_node('seteuk_intro', seteuk_intro)
    graph.add_node('seteuk_conclusion', seteuk_conclusion)
    graph.add_node('routing_branch_node', routing_branch_node)
    # Set the Starting Edge
    graph.set_entry_point("protoGenerator") 
    graph.add_edge("protoGenerator", "protoInspector")
    graph.add_edge("protoInspector", "perplexity")

    graph.add_conditional_edges(
        "protoInspector",
        protoInspectorRouter,
        {
            "protoResearch": "call_proto_researcher_graph",
            "None": "routing_branch_node"
        },)
    graph.add_edge("routing_branch_node", "seteuk_body")
    graph.add_edge("routing_branch_node", "seteuk_intro")
    graph.add_edge("routing_branch_node", "seteuk_conclusion")
    graph.add_edge("call_proto_researcher_graph", "seteuk_body")
    graph.add_edge("call_proto_researcher_graph", "seteuk_intro")
    graph.add_edge("call_proto_researcher_graph", "seteuk_conclusion")
    graph.add_edge('seteuk_body', END)
    graph.add_edge('seteuk_intro', END)
    graph.add_edge('seteuk_conclusion', END)
    graph.add_edge('perplexity', END)

    app = graph.compile()
    return app

def run(major, keyword, topic, seteuk_depth):
    app = GraphGenerate()
    response = app.invoke({'major':major, 'keyword': keyword, 'topic': topic, 'seteuk_depth': seteuk_depth
 })

    return  {'proto': response['proto'], 
     'introduction': response['introduction'], 
     'body': response['body'] + '\n\n' + response['case_result'], 
     'conclusion': response['conclusion'],
     'reference_news': response['reference_news'],
     }

