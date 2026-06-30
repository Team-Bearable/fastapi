import os


class WorkerConfig:
    """세특 LLM 스트림 워커 설정 (env 로 오버라이드).

    myfolio(Java)가 요청 메시지를 llm-requests 스트림에 넣으면, 이 워커가 꺼내
    LLM 처리 후 결과를 llm-results 스트림에 넣는다. 스트림·그룹 이름은 myfolio와
    똑같아야 하므로 기본값을 계약값으로 둔다.
    """

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.requests_stream = os.getenv("LLM_REQUESTS_STREAM", "myfolio:stream:llm-requests")
        self.results_stream = os.getenv("LLM_RESULTS_STREAM", "myfolio:stream:llm-results")
        # 요청 스트림을 읽을 컨슈머 그룹. myfolio 는 넣기만 하니 이 그룹은 워커가 만든다.
        self.group = os.getenv("LLM_REQUESTS_GROUP", "llm-workers")
        # 컨슈머 이름은 고정한다 — 워커가 죽었다 살아나면 이 이름으로 "아직 완료 처리 안 한"
        # 메시지를 다시 집어오기 때문. 여러 대로 늘릴 땐 대마다 다른 이름을 준다.
        self.consumer = os.getenv("LLM_WORKER_CONSUMER", "myfolio-llm-worker")
        self.batch = int(os.getenv("LLM_WORKER_BATCH", "10"))
        self.block_ms = int(os.getenv("LLM_WORKER_BLOCK_MS", "1000"))
        self.poll_interval = float(os.getenv("LLM_WORKER_POLL_INTERVAL", "0.1"))
        self.max_concurrent = int(os.getenv("LLM_WORKER_MAX_CONCURRENT", "5"))
