"""애플리케이션 로깅 설정.

배포 환경(개발/운영 클라우드)에서는 GCP Cloud Logging이 자동으로 필드를 전개할 수 있도록
stdout에 **한 줄 JSON**으로 로그를 출력한다. 로컬(ENV=local 또는 미설정)에서는 기존처럼
사람이 읽기 쉬운 평문 로그를 유지한다.

백엔드(Spring)와 키를 통일: severity / message / logger / timestamp.
추가 컨텍스트 필드는 `extra=`로 넘기면 그대로 JSON 최상위 필드로 전개된다.

    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("작업 완료", extra={"request_id": rid, "job_type": job, "duration_ms": ms})
"""

import logging
import os
import sys
from datetime import datetime, timezone

from pythonjsonlogger.json import JsonFormatter

# ENV 값이 아래에 속하면 JSON 구조화 로깅을 사용한다(클라우드 배포 상태).
_CLOUD_ENVS = {"development", "production"}


def _is_cloud_env() -> bool:
    return os.getenv("ENV", "local").strip().lower() in _CLOUD_ENVS


class GcpJsonFormatter(JsonFormatter):
    """GCP Cloud Logging용 한 줄 JSON 포매터.

    백엔드(Spring)와 동일한 키로 출력한다:
    - severity: Python 로그 레벨명 (GCP LogSeverity와 호환)
    - message: 포맷팅된 로그 메시지 (JsonFormatter 기본)
    - logger: record.name
    - timestamp: ISO8601 (UTC, 'Z' suffix)

    `extra=`로 넘긴 커스텀 필드(request_id, job_type 등)와 예외 정보(exc_info)는
    JsonFormatter가 자동으로 최상위 필드로 전개한다. 멀티라인 스택트레이스도
    한 JSON 필드(exc_info 문자열)로 들어가 라인별로 쪼개지지 않는다.
    """

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["severity"] = record.levelname
        log_record["logger"] = record.name
        log_record["timestamp"] = (
            datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )


def setup_logging(level: str | None = None) -> None:
    """루트 로거와 uvicorn 로거를 환경에 맞는 핸들러/포매터로 재구성한다.

    uvicorn은 기동 시 자체 로거(uvicorn/uvicorn.access/uvicorn.error)에 평문 핸들러를
    붙이므로, 이 함수에서 해당 핸들러를 제거하고 루트로 전파시켜 포맷을 통일한다.
    앱 import 시점(uvicorn의 로깅 설정 이후)에 호출되어야 우리 설정이 최종 적용된다.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    if _is_cloud_env():
        # ensure_ascii=False: 한글 메시지를 그대로 출력. message 키는 JsonFormatter 기본.
        handler.setFormatter(GcpJsonFormatter(json_ensure_ascii=False))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn 로거들이 자체 평문 핸들러로 직접 출력하지 않고 루트로 전파하도록 통일.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """모듈용 로거를 반환한다. `print()` 대신 사용 권장.

    from utils.logger import get_logger
    logger = get_logger(__name__)
    """
    return logging.getLogger(name)
