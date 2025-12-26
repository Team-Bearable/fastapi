"""
워드 클라우드 생성 서비스 모듈

이 모듈은 키워드 리스트로부터 워드 클라우드 이미지를 생성합니다.
"""

from .index import generate_word_cloud

__all__ = ['generate_word_cloud']
