"""
키워드 추출 서비스 모듈

이 모듈은 세특 콘텐츠에서 빈도 기반 raw_weight가 부여된 키워드를 추출합니다.
"""

from .index import extract_keywords

__all__ = ['extract_keywords']
