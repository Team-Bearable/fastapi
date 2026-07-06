import asyncio

from worker.errors import UnsupportedJobType
from worker.handlers import saenggibu, seteuk


_HANDLERS = {
    "SETEUK_TOPIC_RECOMMEND": seteuk.handle_topic_recommend,
    "SETEUK_GUIDELINE_GENERATE": seteuk.handle_guideline_generate,
    "RECORD_EXTRACT": saenggibu.handle_record_extract,
    "ACTIVITY_EXTRACT": saenggibu.handle_activity_extract,
    "TAGGING": saenggibu.handle_tagging,
}


async def dispatch(job_type: str, payload: dict) -> dict:
    handler = _HANDLERS.get(job_type)
    if handler is None:
        raise UnsupportedJobType(job_type)
    # async 핸들러(비블로킹 LLM)는 이벤트 루프에서 await, sync 핸들러(블로킹 LLM/OCR)는 스레드로.
    if asyncio.iscoroutinefunction(handler):
        return await handler(payload)
    return await asyncio.to_thread(handler, payload)
