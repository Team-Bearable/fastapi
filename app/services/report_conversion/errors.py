"""report_conversion 도메인 예외.

워커 계층(app.worker.errors)에 의존하지 않도록 서비스가 자기 예외를 소유한다.
핸들러가 이걸 잡아 JobFailed(errorCode)로 변환해 결과 스트림에 싣는다.
"""


class ContentPolicyError(Exception):
    """모델이 콘텐츠 정책으로 생성을 거부(refusal)함 → errorCode LLM_CONTENT_POLICY."""


class ConversionError(Exception):
    """활동 서술로 정규화할 수 없는 입력(빈 내용에 가까운 잡담 등). 억지 생성 대신 명시적 실패."""
