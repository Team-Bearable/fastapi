"""스트림 소비 배관 테스트 — fakeredis + 가짜 핸들러(LLM 미사용)."""

import asyncio
import json
import os
import time

import fakeredis
import pytest

from worker import dispatch
from worker.config import WorkerConfig
from worker.consumer import StreamConsumer


@pytest.fixture(autouse=True)
def echo_handler():
    # 배관만 검증하도록 결정적 echo 핸들러를 등록(테스트 후 제거).
    dispatch._HANDLERS["TEST_ECHO"] = lambda payload: {"echo": payload}
    yield
    dispatch._HANDLERS.pop("TEST_ECHO", None)


@pytest.fixture
def env():
    server = fakeredis.FakeServer()
    cfg = WorkerConfig()
    cfg.block_ms = 50          # 테스트 속도
    cfg.poll_interval = 0.01
    consumer = StreamConsumer(cfg)
    consumer.client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    client = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return consumer, client, cfg


def _envelope(job_type, payload, request_id="r1"):
    return {
        "requestId": request_id, "jobId": "j1", "taskIndex": "0",
        "jobType": job_type, "payload": json.dumps(payload, ensure_ascii=False),
        "enqueuedAt": str(int(time.time() * 1000)),
    }


async def _run_until(consumer, client, cfg, n_results):
    await consumer.start()  # 내부에서 백그라운드 러너를 띄우고 즉시 반환
    try:
        for _ in range(200):
            res = await client.xrange(cfg.results_stream)
            if len(res) >= n_results:
                return res
            await asyncio.sleep(0.02)
        return await client.xrange(cfg.results_stream)
    finally:
        await consumer.stop()


async def test_roundtrip_success(env):
    consumer, client, cfg = env
    await client.xadd(cfg.requests_stream, _envelope("TEST_ECHO", {"hello": "세계"}))

    res = await _run_until(consumer, client, cfg, 1)

    assert len(res) == 1
    _id, f = res[0]
    assert f["requestId"] == "r1"
    assert f["status"] == "SUCCEEDED"
    assert json.loads(f["result"]) == {"echo": {"hello": "세계"}}  # 한글 보존
    assert "enqueuedAt" in f
    # 처리 후 ack → pending 0
    assert (await client.xpending(cfg.requests_stream, cfg.group))["pending"] == 0


async def test_roundtrip_unknown_jobtype(env):
    consumer, client, cfg = env
    await client.xadd(cfg.requests_stream, _envelope("NOPE", {}, request_id="r2"))

    res = await _run_until(consumer, client, cfg, 1)

    _id, f = res[0]
    assert f["requestId"] == "r2"
    assert f["status"] == "FAILED"
    assert f["errorCode"] == "UNSUPPORTED_JOB_TYPE"
    # 실패도 결과 발행 후 ack
    assert (await client.xpending(cfg.requests_stream, cfg.group))["pending"] == 0


async def test_invalid_depth_maps_to_invalid_payload(env):
    consumer, client, cfg = env
    await client.xadd(cfg.requests_stream, _envelope(
        "SETEUK_TOPIC_RECOMMEND",
        {"major": "x", "keyword": "k", "seteukDepth": "HARD"},  # 미지원 depth
        request_id="r-depth",
    ))

    res = await _run_until(consumer, client, cfg, 1)

    _id, f = res[0]
    assert f["status"] == "FAILED"
    assert f["errorCode"] == "INVALID_PAYLOAD"  # LLM_FAILED 로 뭉뚱그리지 않음


async def test_malformed_json_maps_to_invalid_payload(env):
    consumer, client, cfg = env
    await client.xadd(cfg.requests_stream, {
        "requestId": "r-json", "jobId": "j1", "taskIndex": "0",
        "jobType": "TEST_ECHO", "payload": "not-json", "enqueuedAt": "0",
    })

    res = await _run_until(consumer, client, cfg, 1)

    _id, f = res[0]
    assert f["status"] == "FAILED"
    assert f["errorCode"] == "INVALID_PAYLOAD"


async def test_restart_recovery():
    # 재시작 복구는 xreadgroup("0")로 자기 PEL(미ack)을 재조회하는데, fakeredis 가 이를
    # 지원하지 않아 실 redis 로만 검증한다. redis 미가용 환경에선 skip.
    import redis.asyncio as aredis

    url = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    probe = aredis.Redis.from_url(url, decode_responses=True)
    try:
        await probe.ping()
    except Exception:
        await probe.aclose()
        pytest.skip("real redis 미가용 — 재시작 복구 테스트 skip")

    cfg = WorkerConfig()
    cfg.redis_url = url
    cfg.block_ms = 50
    cfg.poll_interval = 0.01
    cfg.requests_stream = "test:llm-requests"
    cfg.results_stream = "test:llm-results"
    cfg.group = "test-workers"
    cfg.consumer = "test-consumer"
    consumer = StreamConsumer(cfg)  # 실 redis 클라이언트를 스스로 생성

    try:
        await probe.delete(cfg.requests_stream, cfg.results_stream)
        await probe.xgroup_create(cfg.requests_stream, cfg.group, id="0", mkstream=True)
        await probe.xadd(cfg.requests_stream, _envelope("TEST_ECHO", {"x": 1}, request_id="r3"))
        # 크래시 시뮬레이션: 같은 consumer 이름으로 받기만 하고 ack 안 함 → PEL 에 남음
        await probe.xreadgroup(cfg.group, cfg.consumer, {cfg.requests_stream: ">"}, count=10)
        assert (await probe.xpending(cfg.requests_stream, cfg.group))["pending"] == 1

        # 재시작: 같은 이름으로 start → _drain_pending("0")이 재처리
        res = await _run_until(consumer, probe, cfg, 1)

        _id, f = res[0]
        assert f["requestId"] == "r3"
        assert f["status"] == "SUCCEEDED"
        assert (await probe.xpending(cfg.requests_stream, cfg.group))["pending"] == 0
    finally:
        await probe.delete(cfg.requests_stream, cfg.results_stream)
        await probe.aclose()
