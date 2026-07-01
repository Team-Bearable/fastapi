"""워커 공용 예외 — dispatch·handlers·consumer 가 함께 쓴다(순환 import 회피)."""


class UnsupportedJobType(Exception):
    """이 워커가 모르는 jobType. 결과 스트림에 실패(FAILED)로 돌려보낸다."""


class InvalidPayload(Exception):
    """요청 payload 가 계약과 안 맞음 — 필수 필드 누락·미지원 값 등. 재시도해도 같다."""
