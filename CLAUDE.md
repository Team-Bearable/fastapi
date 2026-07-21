# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**마이폴리오(MyFolio) 서비스의 LLM 요청 처리 워커 모듈.** LangChain/LangGraph 기반으로 교육
콘텐츠(세특 가이드라인, 키워드, 제출물 분석, 워드클라우드)를 생성한다. Claude Sonnet, GPT-4o,
Perplexity 등 멀티 AI 모델을 사용한다.

**아키텍처 전환 중:** 웹 API(HTTP 요청/응답) 방식에서 **Redis Stream 메시지 소비·생성** 방식으로
이전하고 있다. 플랫폼(myfolio, Java/Spring)이 `llm-requests` 스트림에 작업을 넣으면 이 워커가
꺼내 LLM 처리 후 결과를 `llm-results` 스트림에 넣는다. FastAPI 앱은 유지되지만(웹 서버 겸 워커
호스트), **주 실행 경로는 워커**이고 `app/routers/`의 HTTP 엔드포인트는 레거시다(전환 완료 시 제거 대상).

**배포:** GCP Compute Engine VM에 Docker 컨테이너로 배포된다. (과거 AWS Lambda/Mangum 배포는 폐기됨 — 관련 잔재를 발견하면 정리 대상으로 간주하라.)

## 설계 원칙 (반드시 지킬 것)

이 프로젝트는 구조적 안정성·확장성을 위해 아래 제약을 따른다. 변경 시 위배하지 말 것:

1. **Python / FastAPI 베스트 프랙티스** — 최신 컨벤션(타입 힌트, 절대 import, async 우선)을 따른다.
2. **소비자-생산자 패턴** — `StreamConsumer`가 요청 스트림을 소비하고 결과 스트림을 생산한다.
   워커는 **도메인을 몰라야** 한다(generic worker). 도메인 실패는 `JobFailed(code, msg)`로 감싸
   전달하여 consumer가 코드만 결과에 싣게 한다.
3. **전략 패턴** — jobType → 핸들러 매핑(`app/worker/dispatch.py`의 `_HANDLERS`). **새 작업 유형
   추가 = 새 핸들러 함수 + `_HANDLERS`에 등록**. consumer/dispatch 코어는 건드리지 않는다.
4. **구조적 로깅** — GCP Cloud Logging 수집을 위해 한 줄 JSON 로그. 아래 "로깅" 섹션의 규약 준수.
5. **페이로드 경량 원칙** — 이미지·PDF 같은 본문은 스트림에 싣지 않는다. presigned URL(S3)로 워커가
   직접 다운로드/업로드하고, 저장 위치 소유권은 플랫폼(Java)이 유지한다.

## 개발 명령어

```bash
# 의존성 설치 (개발: 테스트 도구 포함)
pip install -r requirements-dev.txt      # 운영은 requirements.txt

# 로컬 실행 (uvicorn; lifespan 이 스트림 컨슈머를 백그라운드로 기동)
uvicorn app.main:app --host 0.0.0.0 --port 8000
#   → 로컬에서 워커를 돌리려면 REDIS_URL 이 가리키는 Redis 가 떠 있어야 한다.

# Docker Compose (localhost:8000 → 컨테이너 8000, ENV=local)
docker-compose up --build

# 테스트 (pytest.ini: testpaths=tests, asyncio_mode=auto)
pytest                                    # 전체
pytest tests/test_stream_consumer.py      # 파일 단위
pytest tests/test_stream_consumer.py::test_publish_failure_keeps_pending   # 단일 테스트
```

테스트는 `fakeredis`로 Redis를, `tests/conftest.py`의 스텁으로 실제 LLM 서비스를 대체한다 —
워커 "배관"(소비·발행·ack·복구)만 검증하며 LLM은 호출하지 않는다.

## 환경 변수

`.env` 파일 (또는 컨테이너 env):
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`
- `REDIS_URL` — 기본 `redis://localhost:6379/0`
- `ENV` — `local` / `development` / `production` (`development`·`production`에서만 JSON 로깅)
- 워커 튜닝(선택, `app/worker/config.py` 참조): `LLM_REQUESTS_STREAM`, `LLM_RESULTS_STREAM`,
  `LLM_REQUESTS_GROUP`, `LLM_WORKER_CONSUMER`, `LLM_WORKER_MAX_CONCURRENT`,
  `LLM_WORKER_BATCH`, `LLM_WORKER_RECLAIM_IDLE_MS` 등. 스트림·그룹 기본값은 myfolio와의 **계약값**이니
  임의로 바꾸지 말 것.

## 아키텍처

### 요청 흐름 (주 경로)

```
myfolio(Java) → XADD llm-requests
                      ↓
   StreamConsumer.(_loop) XREADGROUP → dispatch(jobType, payload) → 핸들러 → Service(LangGraph)
                      ↓
   XADD llm-results (SUCCEEDED/FAILED) → XACK   (발행 성공 후에만 ack)
```

4계층: **Worker**(`app/worker/`) → **Handler**(`app/worker/handlers/`) → **Service**
(`app/services/`, LangGraph 워크플로우) → **Utils**(`app/utils/`: model, 프롬프트, logger).
핸들러는 Java 페이로드 ↔ 서비스 인자/결과의 **경계 변환**만 담당하고 LLM 로직은 서비스에 있다.

### 워커 (`app/worker/`) — 핵심 메커니즘

`consumer.py`의 `StreamConsumer`는 FastAPI lifespan에서 백그라운드 태스크로 돈다.
아래는 코드에 반영된 신뢰성 설계이니 리팩터링 시 깨뜨리지 말 것:

- **자가복구**: 부팅 시 Redis 불가 등 연결/실행 실패해도 죽지 않고 백오프(1→30s)로 재연결.
  `start()`는 즉시 반환하여 Redis 장애가 HTTP 기동을 막지 않는다.
- **at-least-once**: 결과 발행(`_publish`)이 성공한 뒤에만 `xack`. 발행 실패 시 미ack로 남겨
  재시작·reclaim이 다시 처리하게 한다.
- **재시작 복구**(`_drain_pending`): 이 컨슈머의 PEL(처리하다 만 메시지)을 커서 페이징으로 전부 회수.
- **멀티 인스턴스 안전**: 컨슈머 이름 기본값을 `host+pid`로 유니크하게. 죽은 인스턴스의 idle 메시지는
  `XAUTOCLAIM`(`_reclaim`)으로 회수. `reclaim_min_idle_ms`(기본 180s)는 **가장 느린 작업
  (가이드라인 ~95s)보다 크고 Java 타임아웃(240s)보다 작아야** 처리 중 메시지를 뺏지 않는다.
- **동시성 제어**: `Semaphore(max_concurrent)`로 동시 처리 수 제한 — 처리 속도보다 빨리 읽지 않는다.
- **sync/async 디스패치**(`dispatch.py`): async 핸들러(비블로킹 LLM)는 `await`, sync 핸들러
  (블로킹 LLM/이미지 생성)는 `asyncio.to_thread`로 돌려 이벤트 루프를 막지 않는다.

### jobType → 핸들러 → 서비스

| jobType | 핸들러 | 서비스 | 입력→출력 (Java 계약) |
|---------|--------|--------|----------------------|
| `SETEUK_TOPIC_RECOMMEND` | `seteuk.handle_topic_recommend` | `difficulty_service_distil2` | `{major, keyword, seteukDepth}` → `{topics:[{topic,tip,keyword}]}` |
| `SETEUK_GUIDELINE_GENERATE` | `seteuk.handle_guideline_generate` | `difficulty_service_distil2` | `{major, keywords[], topic, seteukDepth}` → `{introduction, body, conclusion, referenceNews[]}` |
| `KEYWORD_EXTRACTION` | `keyword.handle_keyword_extraction` | `keyword_extraction` | `{...info, guideline{...}}` → `{keywords:[{keyword, raw_weight}]}` |
| `SUBMISSION_ANALYSIS` | `submission.handle_submission_analysis` (async) | `submission_analyze` | `{presignedUrl, ...}` → `{summary, review}` (PDF는 presignedUrl로 다운로드) |
| `WORD_CLOUD` | `wordcloud.handle_word_cloud` | `word_cloud` | `{keywords[], font, color, mask, uploadUrl}` → `{}` (PNG를 uploadUrl로 PUT) |

**난이도 매핑** (Java 값 → 프롬프트 표현, `handlers/seteuk.py`): `BASIC→Basic`,
`INTERMEDIATE→Applied`, `ADVANCED→Advanced`. (레거시 라우터의 `기초/응용/심화` 매핑과 별개.)

### 오류 코드 (`consumer._error_code`)

결과 스트림의 `errorCode`로 나가며 실패 성격을 구분한다:
- `INVALID_PAYLOAD` — 필수 필드 누락·미지원 값·JSON 파싱 실패(입력 계약 위반, 재시도 무의미)
- `UNSUPPORTED_JOB_TYPE` — 이 워커가 모르는 jobType
- 도메인 코드 (예 `WORD_CLOUD_FAILED`) — 핸들러가 `JobFailed(code, ...)`로 지정
- `LLM_FAILED` — 그 외 예상 못한 실패(유일하게 traceback 을 남김)

### LangGraph 서비스 변형

`app/services/`에 difficulty_service의 세 변형이 공존한다:
- **`difficulty_service_distil2`** — **워커가 실제로 쓰는 것.** 메인과 유사하나 토큰/비용 추적 포함.
- `difficulty_service` (메인, 프로토 검증+리서치 서브그래프) / `difficulty_service_distil` (검증 생략
  직선형) — 레거시 HTTP 라우터가 참조. 신규 작업은 distil2 계열을 기준으로 한다.

### 모델 (`app/utils/model.py`)

상수로 모델명 관리: `ANTHROPIC_MODEL`(claude-sonnet-4-6, 주력), `OPENAI_MODEL`(gpt-4o, 자료 정리),
`OPENAI_MINI_MODEL`(gpt-4o-mini), `PERPLEXITY_MODEL`(sonar, 시사 검색). `anthropic_async`는
비블로킹 async 클라이언트. 프롬프트는 `app/utils/*_prompt.py`의 클래스 기반(`system`/`human`/`tip` 속성).

### 절대 import 규약

`app`이 최상위 Python 패키지다(모든 하위 폴더에 `__init__.py` 존재). first-party import는
**`app.` 접두 절대 import**로 쓴다 — `from app.worker.consumer import ...`,
`from app.services.difficulty_service_distil2.difficulty_graph import run`,
`from app.utils.logger import get_logger`. import 루트는 저장소 루트이며, 실행 컨텍스트가
이를 보장한다: 앱은 `uvicorn app.main:app`(cwd=저장소 루트), 테스트는 `pytest.ini`의
`pythonpath = .`. **`sys.path` 조작 금지** — 과거의 `sys.path.append` 해킹은 제거되었으니
되살리지 말 것. 같은 패키지 내부 `__init__.py`에서는 상대 import(`from .index import ...`)도 무방.

## 로깅 (필수 규약)

`utils/logger.py`의 `get_logger()`를 쓰고 `print()`는 쓰지 않는다. `setup_logging()`은 앱/워커
import보다 먼저 호출된다.

- **형식**: `ENV`가 `development`/`production`이면 한 줄 JSON(`GcpJsonFormatter`)으로 stdout에 출력 →
  GCP Cloud Logging이 필드를 전개. 로컬은 평문. 키는 백엔드(Spring)와 통일: `severity` / `message` /
  `logger` / `timestamp`.
- **컨텍스트 필드**: `logger.info("...", extra={"request_id": rid, "job_type": job, "duration_ms": ms})`
  처럼 `extra=`로 넘기면 JSON 최상위 필드로 전개된다.
- **필수 로그 1 — 메시지 라이프사이클**: consumer가 `consumed` / `succeeded` / `failed`를 남기며
  `requestId`, `jobType`, `elapsed`(처리 시간)를 포함한다. **jobType별 처리 시간을 로그로 확인**
  가능해야 한다(정확한 값은 플랫폼 DB에 기록되므로 로그는 관측 수준이면 충분). 새 처리 경로도 이 3단계를
  남길 것.
- **필수 로그 2 — 외부 요청(LLM API)**: LLM/외부 API 호출은 구조적 로그로 남긴다(요청 식별자·모델·
  소요시간 등). 신규 서비스/핸들러에서 외부 호출을 추가하면 반드시 로깅을 함께 넣는다.
- **민감 데이터**: 학생 데이터가 든 `payload`는 평시 남기지 않고 `DEBUG`에서만 남긴다.

## 코드 패턴 및 주의사항

- **LangGraph 노드**: state dict를 받아 **업데이트할 필드만** 반환. 병렬 실행은 같은 노드에서 여러
  엣지를 추가.
- **JSON 파싱**(`app/utils/utils.py`): `json_format()`(정규식)·`perple_json_format()`(`ast.literal_eval`).
  일부 레거시 코드에 `eval()` 잔존(예 `app/routers/difficulty.py`) — 보안상 `json.loads()`로 교체 대상.
- **레거시 라우터**: `app/routers/`의 HTTP 엔드포인트는 스트림 전환의 잔재다. 신규 기능은 워커 경로
  (jobType + 핸들러)로 추가하고 라우터를 늘리지 말 것.
