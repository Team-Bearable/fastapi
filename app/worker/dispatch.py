from worker.handlers import seteuk


class UnsupportedJobType(Exception):
    """이 워커가 모르는 jobType. 결과 스트림에 실패(FAILED)로 돌려보낸다."""


_HANDLERS = {
    "SETEUK_TOPIC_RECOMMEND": seteuk.handle_topic_recommend,
    "SETEUK_GUIDELINE_GENERATE": seteuk.handle_guideline_generate,
}


def dispatch(job_type: str, payload: dict) -> dict:
    handler = _HANDLERS.get(job_type)
    if handler is None:
        raise UnsupportedJobType(job_type)
    return handler(payload)
