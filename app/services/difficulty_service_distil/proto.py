from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from utils.difficulty_prompt_distil import seteukBasicProto
from utils.model import anthropic
from utils.utils import json_format


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
    try:
        json_result = json_format(result)
    except Exception as final_e:
        print("Final proto parsing error:", final_e)
        print("proto 값:", result)
    return {"messages": [json_result], 'proto': json_result}