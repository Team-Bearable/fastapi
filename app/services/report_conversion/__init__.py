"""활동 리포트 변환 서비스 모듈.

활동 리포트 원문을 생기부 기재 문체 활동 서술 1건으로 요약·정규화한다.
"""
from .index import convert_report
from .errors import ContentPolicyError, ConversionError

__all__ = ["convert_report", "ContentPolicyError", "ConversionError"]
