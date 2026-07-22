import asyncio

from app.worker.errors import UnsupportedJobType
from app.worker.handlers import keyword, seteuk, submission, wordcloud


_HANDLERS = {
    "SETEUK_TOPIC_RECOMMEND": seteuk.handle_topic_recommend,
    "SETEUK_GUIDELINE_GENERATE": seteuk.handle_guideline_generate,
    "KEYWORD_EXTRACTION": keyword.handle_keyword_extraction,
    "SUBMISSION_ANALYSIS": submission.handle_submission_analysis,
    "WORD_CLOUD": wordcloud.handle_word_cloud,
    "SETEUK_PLUS_GENERATE": seteuk.handle_plus_generate,
}


async def dispatch(job_type: str, payload: dict) -> dict:
    handler = _HANDLERS.get(job_type)
    if handler is None:
        raise UnsupportedJobType(job_type)
    # async 핸들러(비블로킹 LLM)는 이벤트 루프에서 await, sync 핸들러(블로킹 LLM/이미지)는 스레드로.
    if asyncio.iscoroutinefunction(handler):
        return await handler(payload)
    return await asyncio.to_thread(handler, payload)
