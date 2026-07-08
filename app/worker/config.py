import os
import socket


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
        # 컨슈머 이름은 인스턴스마다 달라야 한다 — 같은 이름을 여러 인스턴스가 쓰면 한 인스턴스가
        # 뜨면서 다른 인스턴스가 처리 중인 메시지를 회수해 중복 처리한다. 기본값을 host+pid 로
        # 유니크하게. (죽은 인스턴스의 미ack 메시지는 아래 reclaim 이 회수)
        self.consumer = os.getenv("LLM_WORKER_CONSUMER") or f"{socket.gethostname()}-{os.getpid()}"
        self.batch = int(os.getenv("LLM_WORKER_BATCH", "10"))
        self.block_ms = int(os.getenv("LLM_WORKER_BLOCK_MS", "1000"))
        self.poll_interval = float(os.getenv("LLM_WORKER_POLL_INTERVAL", "0.1"))
        self.max_concurrent = int(os.getenv("LLM_WORKER_MAX_CONCURRENT", "5"))
        # 죽은 인스턴스의 미ack 메시지를 회수(XAUTOCLAIM)할 idle 임계(ms). 가장 느린 작업
        # (가이드라인 ~95s)보다 커야 처리 중인 메시지를 뺏지 않는다. Java 타임아웃(240s) 이내.
        self.reclaim_min_idle_ms = int(os.getenv("LLM_WORKER_RECLAIM_IDLE_MS", "180000"))
