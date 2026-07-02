from worker.errors import UnsupportedJobType
from worker.handlers import seteuk


_HANDLERS = {
    "SETEUK_TOPIC_RECOMMEND": seteuk.handle_topic_recommend,
    "SETEUK_GUIDELINE_GENERATE": seteuk.handle_guideline_generate,
}


def dispatch(job_type: str, payload: dict) -> dict:
    handler = _HANDLERS.get(job_type)
    if handler is None:
        raise UnsupportedJobType(job_type)
    return handler(payload)
