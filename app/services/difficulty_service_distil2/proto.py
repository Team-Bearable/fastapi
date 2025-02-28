from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from utils.difficulty_prompt_distil2 import seteukBasicProto, protoInspectorPrompt
from utils.model import anthropic, gpt4o
from utils.utils import json_format
from utils.logging_config import logger 

def protoGenerator(state):
    tp_cs = seteukBasicProto()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    major = state['major']
    keyword = state['keyword']
    topic = state['topic']
    seteuk_depth = state['seteuk_depth']
    chain  = {"major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'topic': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result = chain.invoke({'major':major, 'keyword':keyword, 'topic': topic, 'seteuk_depth': seteuk_depth})
    json_result = None
    try:
        json_result = json_format(result)
    except Exception as e:
        logger.exception("Error during protoResearcher: %s", e)
    return {'proto': json_result}

def protoInspector(state):
    tp_cs = protoInspectorPrompt()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.context),
        ]
    )
    major = state['major']
    keyword = state['keyword']
    topic = state['topic']
    seteuk_depth = state['seteuk_depth']
    proto = state['proto']
    chain_gpt  = {"major": RunnablePassthrough(), 'keyword': RunnablePassthrough(), 'topic': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough(), 'proto': RunnablePassthrough()}|topic_prompt | gpt4o | StrOutputParser()
    result_inspector = chain_gpt.invoke({'major':major, 'keyword':keyword, 'topic': topic, 'seteuk_depth': seteuk_depth, 'proto': proto})
    try:
        result = eval(result_inspector)['Response']
    except Exception as e:
        logger.exception("Error during protoInspector: %s", e)
    return {"n_proto_research": len(result), "result_inspect": result}


def protoInspectorRouter(state):
    messages = state["result_inspect"]
    # last_message = messages[-1]
    # last_message = messages[-1]
    # if len(last_message) > 0:
    try:
        if state['n_proto_research'] > 0:
            return 'protoResearch'
        else:
            print('검사 결과:', 'None')
            return 'None'
    except Exception as e:
        logger.exception("Error during protoInspectorRouter: %s", e)