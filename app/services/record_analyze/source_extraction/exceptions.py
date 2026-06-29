"""원문추출 패키지 공개 예외."""


class UnsupportedRecordFormatError(Exception):
    """분석 미지원 생기부 포맷 신호 — 호출측이 분석을 건너뛰고 거절(reject)하도록.

    예: 2011 개정 이전 교육과정('창의적 재량활동상황'+'특별활동상황'). OCR/파서 결함에
    의한 일반 추출 실패(RuntimeError)와 구분해, '미지원 포맷'으로 의도적 거절할 때 쓴다.
    """

    def __init__(self, message: str = "2011 개정 이전 교육과정 포맷(재량활동/특별활동) — 분석 미지원"):
        super().__init__(message)


class OcrError(Exception):
    """Vision OCR 페이지 호출이 재시도까지 소진하고 실패. 부분 출력은 하지 않는다.

    한 페이지라도 실패하면 레코드 누락 위험이 있어 문서 전체를 이 예외로 실패시킨다.
    호출측(워커)이 '일시성 OCR 실패 → 문서 단위 재시도/DLQ' 대상으로 판단하게 한다.
    """

