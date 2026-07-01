import asyncio
import json
import logging
import time

import redis.asyncio as redis

from worker import dispatch
from worker.errors import InvalidPayload, UnsupportedJobType

log = logging.getLogger("llm_worker")

_SUCCEEDED = "SUCCEEDED"
_FAILED = "FAILED"

# 연결/기동 실패 시 재시도 대기(지수 백오프, 초).
_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


class StreamConsumer:
    """요청 스트림에서 메시지를 꺼내 LLM 으로 처리하고, 결과를 결과 스트림에 넣는 소비자.

    FastAPI 가 켜질 때 백그라운드로 함께 돈다. 시작하면 먼저 지난 실행에서 처리하다 만
    메시지를 다시 처리하고, 그다음부터 새 메시지를 계속 기다린다. 한 번에 처리하는 개수는
    제한하며(config.max_concurrent), 시간이 오래 걸리는 LLM 호출은 별도 스레드에서 돌려
    웹 요청 등 다른 일이 멈추지 않게 한다.
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
                backoff = _MIN_BACKOFF  # 연결 성공 → 백오프 리셋
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
        # 이 스트림을 읽을 그룹을 만든다. 이미 있으면(BUSYGROUP) 그냥 넘어가고, 그 외 오류는 던진다.
        try:
            await self.client.xgroup_create(
                self.cfg.requests_stream, self.cfg.group, id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _drain_pending(self):
        # 재시작 복구 — 지난번에 받아서 처리하다 만(아직 "완료" 표시 안 한) 메시지를 먼저 다시 가져온다.
        # ("0" = 내가 받았지만 아직 못 끝낸 것들)
        entries = await self.client.xreadgroup(
            self.cfg.group, self.cfg.consumer,
            {self.cfg.requests_stream: "0"}, count=self.cfg.batch,
        ) or []
        await self._spawn(entries)

    async def _loop(self):
        while self.running:
            try:
                # 새 메시지를 기다린다(">" = 아직 아무도 안 가져간 새 것). block(ms)만큼 없으면 잠깐 쉬고 다시.
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
        started = time.monotonic()
        log.info("consumed msgId=%s requestId=%s jobType=%s", msg_id, request_id, job_type)
        # payload 에는 학생 데이터가 들어가고 길 수 있어 평소엔 안 남기고 DEBUG 일 때만 남긴다.
        log.debug("payload requestId=%s %s", request_id, fields.get("payload"))
        try:
            payload = json.loads(fields.get("payload") or "{}")
            result = await asyncio.to_thread(dispatch.dispatch, job_type, payload)
            await self._publish({
                "requestId": request_id,
                "status": _SUCCEEDED,
                "result": json.dumps(result, ensure_ascii=False),
            })
            log.info("succeeded requestId=%s jobType=%s elapsed=%.2fs",
                     request_id, job_type, time.monotonic() - started)
        except Exception as e:
            code = _error_code(e)
            await self._publish({
                "requestId": request_id,
                "status": _FAILED,
                "errorCode": code,
                "errorMessage": str(e),
            })
            elapsed = time.monotonic() - started
            if code == "LLM_FAILED":
                # 예상 못한 실패만 traceback 을 남긴다.
                log.exception("failed requestId=%s jobType=%s errorCode=%s elapsed=%.2fs",
                              request_id, job_type, code, elapsed)
            else:
                # 계약성 실패(미지원 jobType·잘못된 payload)는 요약만.
                log.warning("failed requestId=%s jobType=%s errorCode=%s: %s",
                            request_id, job_type, code, e)
        finally:
            # 결과(성공이든 실패든)를 내보낸 메시지는 다 끝난 것이므로 "완료" 표시(ack)한다.
            # ack 해야 같은 메시지를 다시 받지 않는다.
            await self.client.xack(self.cfg.requests_stream, self.cfg.group, msg_id)

    async def _publish(self, fields):
        fields["enqueuedAt"] = str(int(time.time() * 1000))
        await self.client.xadd(self.cfg.results_stream, fields)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, UnsupportedJobType):
        return "UNSUPPORTED_JOB_TYPE"
    # payload 계약 위반(필수 필드 누락·미지원 값)과 JSON 파싱 실패는 입력 문제.
    if isinstance(exc, (InvalidPayload, json.JSONDecodeError)):
        return "INVALID_PAYLOAD"
    return "LLM_FAILED"
