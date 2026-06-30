import ast

from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from utils.model import anthropic
from utils.difficulty_prompt_distil2 import seteukBasicTopic


def recommend_topics(major: str, keyword: str, seteuk_depth: str) -> list[str]:
    """키워드 1개로 주제 3개를 추천. 각 항목은 "topic::tip::검색어" 문자열.

    seteuk_depth 는 프롬프트가 받는 영문 난이도(Basic/Applied/Advanced)다.
    """
    tp = seteukBasicTopic()
    topic_prompt = ChatPromptTemplate.from_messages(
        [("system", tp.system), ("user", tp.human)]
    )
    tip_prompt = ChatPromptTemplate.from_messages([("user", tp.tip)])

    topic_chain = (
        {
            "major": RunnablePassthrough(),
            "keyword": RunnablePassthrough(),
            "seteuk_depth": RunnablePassthrough(),
        }
        | topic_prompt
        | anthropic
        | StrOutputParser()
    )
    topic_result = topic_chain.invoke(
        {"major": major, "keyword": keyword, "seteuk_depth": seteuk_depth}
    )

    tip_chain = (
        {
            "major": RunnablePassthrough(),
            "keyword": RunnablePassthrough(),
            "topics": RunnablePassthrough(),
        }
        | tip_prompt
        | anthropic
        | StrOutputParser()
    )
    tip_result = tip_chain.invoke(
        {"major": major, "keyword": keyword, "topics": topic_result}
    )
    return ast.literal_eval(tip_result)
