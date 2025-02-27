from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from utils.difficulty_prompt_distil import seteukBasicBodyTop, seteukBasicIntroduction, seteukBasicCoclusion
from utils.model import anthropic, perple, perplexity_model, gpt4o
import json


def seteuk_intro(state):
    print('seteuk_intro 진입')
    topic = state['topic']
    proto = state['proto']
    major = state['major']
    difficulty = state['seteuk_depth']
    # case_result = state['case_result']
    if 'information' in state:
        context = f"""
        REFERENCE INFORMATION:
        {state['information']}
        """
    else:
        context = ""
    tp_cs = seteukBasicIntroduction()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )

    chain  = {"topic": RunnablePassthrough(), 'proto': RunnablePassthrough(), 'major': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result = None
    
    try:
            result = chain.invoke({'topic':topic, 'proto':proto['introduction'], 'major': major, 'seteuk_depth': difficulty})
    except Exception as e:
        print('intro 오류:', e)
    print('intro 끝')
    return {'introduction': result}



def seteuk_body(state):
    print('seteuk_body 진입')
    topic = state['topic']
    proto = state['proto']
    major = state['major']
    difficulty = state['seteuk_depth']
    # case_result = state['case_result']
    if 'information' in state:
        context = f"""
        REFERENCE INFORMATION:
        {state['information']}
        """
    else:
        context = ""
    
    tp_cs = seteukBasicBodyTop()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain  = {"topic": RunnablePassthrough(), 'proto': RunnablePassthrough(), 'major': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough(), 'keyword': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result = None
    result = chain.invoke({'topic':topic, 'proto':proto['body'], 'major': major, 'seteuk_depth': difficulty, 'keyword': state['keyword']})

    return {'body': result}


def seteuk_conclusion(state):
    print('seteuk_conclusion 진입')
    topic = state['topic']
    proto = state['proto']
    major = state['major']
    difficulty = state['seteuk_depth']
    # case_result = state['case_result']
    if 'information' in state:
        context = f"""
        REFERENCE INFORMATION:
        {state['information']}
        """
    else:
        context = ""

    tp_cs = seteukBasicCoclusion()
    topic_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", tp_cs.system),
            ("user", tp_cs.human),
        ]
    )
    chain  = {"topic": RunnablePassthrough(), 'proto': RunnablePassthrough(), 'major': RunnablePassthrough(), 'seteuk_depth': RunnablePassthrough()}|topic_prompt | anthropic | StrOutputParser()
    result = None
    
    try:
            result = chain.invoke({'topic':topic, 'proto':proto['conclusion'], 'major': major,'seteuk_depth': difficulty })
    except Exception as e:
        print('conclusion 오류:', e)
    print('conclusion 끝')
    return {'conclusion': result}
