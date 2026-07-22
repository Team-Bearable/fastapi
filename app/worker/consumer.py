import asyncio
import json
import logging
import time

import redis.asyncio as redis

from app.worker import dispatch
from app.worker.errors import InvalidPayload, JobFailed, UnsupportedJobType

log = logging.getLogger("llm_worker")

_SUCCEEDED = "SUCCEEDED"
_FAILED = "FAILED"

# 실패 분류 코드 — LLM-STREAM-CONTRACT §6.3 카탈로그. myfolio 는 errorCode 를 분기 없이 전파만 한다.
_INVALID_INPUT = "LLM_INVALID_INPUT"   # 입력 계약 위반(필수 필드 누락·미지원 값·JSON 파싱 실패)
_INTERNAL = "LLM_INTERNAL"             # 예상 못한 내부 실패(fallback — traceback 로깅)

_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


class StreamConsumer:
    """요청 스트림에서 메시지를 꺼내 LLM 으로 처리하고, 결과를 결과 스트림에 넣는 소비자.

    FastAPI lifespan 에서 백그라운드로 돈다. 오래 걸리는 LLM 호출은 별도 스레드에서 돌려
    웹 요청을 막지 않고, 동시 처리량은 config.max_concurrent 로 제한한다.
    """

    def __init__(self, config):
        self.cfg = config
        self.client = redis.Redis.from_url(config.redis_url, decode_responses=True)
        self.sem = asyncio.Semaphore(config.max_concurrent)
        self.running = False
        self._tasks: set[asyncio.Task] = set()
        self._runner: asyncio.Task | None = None

    async def start(self):
        # 백그라운드 러너로 띄우고 즉시 반환한다 — Redis 장애가 앱(HTTP) 기동을 막지 않게.
        self.running = True
        self._runner = asyncio.create_task(self._run())

    async def _run(self):
        # 자가복구: 연결/기동이 실패해도 죽지 않고 백오프로 재연결한다(부팅 시 Redis 불가 등).
        backoff = _MIN_BACKOFF
        while self.running:
            try:
                await self._ensure_group()
                log.info(
                    "consumer started stream=%s group=%s consumer=%s",
                    self.cfg.requests_stream, self.cfg.group, self.cfg.consumer,
                )
                backoff = _MIN_BACKOFF
                await self._drain_pending()
                await self._loop()
                return  # _loop 은 running=False(셧다운) 일 때만 정상 반환
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("consumer 연결/실행 실패 — %.1fs 후 재시도", backoff)
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                return
            backoff = min(backoff * 2, _MAX_BACKOFF)

    async def stop(self):
        self.running = False
        # 먼저 읽기 루프를 멈춘다 — 그래야 연결을 닫는 동안 xreadgroup 이 깨지며 나는 오류 로그가 없다.
        if self._runner:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
        # 진행 중인 처리(_handle)가 결과 발행·ack 를 끝내게 기다린 뒤 연결을 닫는다.
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.client.aclose()

    async def _ensure_group(self):
        # 그룹이 이미 있으면(BUSYGROUP) 무시, 그 외 오류는 던진다.
        try:
            await self.client.xgroup_create(
                self.cfg.requests_stream, self.cfg.group, id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _drain_pending(self):
        # 재시작 복구 — 지난번에 받아서 처리하다 만(아직 "완료" 표시 안 한) 메시지를 다시 가져온다.
        # 한 배치만 읽으면 PEL 이 batch 보다 많을 때 나머지가 영영 안 읽히므로, 마지막 id 를
        # 다음 커서로 삼아 빈 결과가 나올 때까지 페이징한다.
        cursor = "0"
        while True:
            entries = await self.client.xreadgroup(
                self.cfg.group, self.cfg.consumer,
                {self.cfg.requests_stream: cursor}, count=self.cfg.batch,
            ) or []
            messages = entries[0][1] if entries and entries[0][1] else []
            if not messages:
                break
            await self._spawn([(self.cfg.requests_stream, messages)])
            cursor = messages[-1][0]

    async def _loop(self):
        while self.running:
            try:
                # 죽은 인스턴스가 남긴 idle 메시지를 먼저 회수(멀티 인스턴스 안전). 있으면 그것부터.
                claimed = await self._reclaim()
                if claimed:
                    await self._spawn([(self.cfg.requests_stream, claimed)])
                    continue
                entries = await self.client.xreadgroup(
                    self.cfg.group, self.cfg.consumer,
                    {self.cfg.requests_stream: ">"},
                    count=self.cfg.batch, block=self.cfg.block_ms,
                ) or []
                if not entries:
                    await asyncio.sleep(self.cfg.poll_interval)
                    continue
                await self._spawn(entries)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("consumer loop error")
                await asyncio.sleep(1)

    async def _reclaim(self):
        # XAUTOCLAIM — 그룹 내 어떤 컨슈머든 min_idle 넘게 미ack 인 메시지를 이 컨슈머로 옮겨온다.
        # 죽은 인스턴스 복구용. idle 임계가 최장 작업보다 커서 처리 중인 메시지는 뺏지 않는다.
        result = await self.client.xautoclaim(
            self.cfg.requests_stream, self.cfg.group, self.cfg.consumer,
            min_idle_time=self.cfg.reclaim_min_idle_ms, count=self.cfg.batch,
        )
        # redis-py: (cursor, messages, deleted). messages = [(id, fields), ...]
        return result[1] if len(result) > 1 else []

    async def _spawn(self, entries):
        for _stream, messages in entries:
            for msg_id, fields in messages:
                # 동시에 처리하는 개수를 max_concurrent 로 제한. 꽉 차 있으면 자리가 날 때까지
                # 여기서 기다리므로, 처리 속도보다 빨리 읽어들이지 않는다.
                await self.sem.acquire()
                task = asyncio.create_task(self._handle(msg_id, fields))
                self._tasks.add(task)
                task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task):
        self._tasks.discard(task)
        self.sem.release()

    async def _handle(self, msg_id, fields):
        request_id = fields.get("requestId")
        job_type = fields.get("jobType")
        # jobId·taskIndex 는 LLM 모듈이 쓰지 않고 추적·상관용으로만 로깅한다(계약 §3).
        job_id = fields.get("jobId")
        task_index = fields.get("taskIndex")
        started = time.monotonic()

        # requestId 가 없으면 ③에 echo 할 상관키가 없어 FAILED 를 발행해도 myfolio 가 Task 에 못 붙인다.
        # 이런 구조적 처리불가 메시지는 결과 스트림 대신 DLQ 로 격리하고 ack 한다(계약 §2, 운영 알람 대상).
        # (payload 역직렬화 실패·미지원 jobType 등은 requestId 로 상관 가능하므로 그대로 FAILED 발행한다.)
        if not request_id:
            await self._to_dlq(msg_id, fields, "MISSING_REQUEST_ID")
            return

        log.info("consumed msgId=%s requestId=%s jobId=%s taskIndex=%s jobType=%s",
                 msg_id, request_id, job_id, task_index, job_type)
        # payload 에는 학생 데이터가 들어가고 길 수 있어 평소엔 안 남기고 DEBUG 일 때만 남긴다.
        log.debug("payload requestId=%s %s", request_id, fields.get("payload"))
        try:
            payload = json.loads(fields.get("payload") or "{}")
            result = await dispatch.dispatch(job_type, payload)
            result_fields = {
                "requestId": request_id,
                "status": _SUCCEEDED,
                "result": json.dumps(result, ensure_ascii=False),
            }
        except Exception as e:
            code = _error_code(e)
            result_fields = {
                "requestId": request_id,
                "status": _FAILED,
                "errorCode": code,
                "errorMessage": str(e),
            }
            elapsed = time.monotonic() - started
            if code == _INTERNAL:
                # 예상 못한 실패만 traceback 을 남긴다.
                log.exception("failed requestId=%s jobType=%s errorCode=%s elapsed=%.2fs",
                              request_id, job_type, code, elapsed)
            else:
                # 계약성 실패(미지원 jobType·잘못된 payload)는 요약만.
                log.warning("failed requestId=%s jobType=%s errorCode=%s: %s",
                            request_id, job_type, code, e)

        # 결과 발행이 성공했을 때만 ack 한다. 발행이 실패하면 메시지를 PEL 에 남겨(ack 안 함)
        # 재시작 복구가 다시 처리하게 한다 — ack 후 발행 실패로 인한 job 유실(at-least-once 약화)을 막는다.
        try:
            await self._publish(result_fields)
            await self.client.xack(self.cfg.requests_stream, self.cfg.group, msg_id)
        except Exception:
            log.exception("결과 발행/ack 실패 — 미ack 로 남겨 복구 대상 requestId=%s", request_id)
            return

        if result_fields["status"] == _SUCCEEDED:
            log.info("succeeded requestId=%s jobType=%s elapsed=%.2fs",
                     request_id, job_type, time.monotonic() - started)

    async def _publish(self, fields):
        fields["enqueuedAt"] = str(int(time.time() * 1000))
        await self.client.xadd(self.cfg.results_stream, fields)

    async def _to_dlq(self, msg_id, fields, reason):
        # 처리불가 메시지를 DLQ 로 격리 후 ack — 원본 스트림이 막히지 않게(계약 §2). 원본 필드를
        # 그대로 싣고 사유·격리시각을 덧붙인다. DLQ 격리(xadd)가 성공해야만 ack 한다 —
        # 실패하면 미ack 로 남겨(PEL) reclaim 이 다시 처리하게 한다.
        entry = dict(fields)
        entry["dlqReason"] = reason
        entry["dlqAt"] = str(int(time.time() * 1000))
        try:
            await self.client.xadd(self.cfg.dlq_stream, entry)
            await self.client.xack(self.cfg.requests_stream, self.cfg.group, msg_id)
        except Exception:
            log.exception("DLQ 격리/ack 실패 — 미ack 로 남겨 복구 대상 msgId=%s reason=%s", msg_id, reason)
            return
        log.warning("DLQ 격리 msgId=%s reason=%s (운영 알람 대상)", msg_id, reason)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, JobFailed):
        return exc.code  # 핸들러가 도메인 실패에 지정한 코드(WORD_CLOUD_FAILED 등)
    if isinstance(exc, UnsupportedJobType):
        return "UNSUPPORTED_JOB_TYPE"
    # payload 계약 위반(필수 필드 누락·미지원 값)과 JSON 파싱 실패는 입력 문제.
    if isinstance(exc, (InvalidPayload, json.JSONDecodeError)):
        return _INVALID_INPUT
    return _INTERNAL
