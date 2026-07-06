"""원문추출 패키지 공개 예외."""


class UnsupportedRecordFormatError(Exception):
    """분석 미지원 생기부 포맷 신호 — 호출측이 분석을 건너뛰고 거절(reject)하도록.

    예: 2011 개정 이전 교육과정('창의적 재량활동상황'+'특별활동상황'). 일시성 OcrError(재시도)와
    달리 재시도해도 같으므로 거절 대상.
    """

    def __init__(self, message: str = "2011 개정 이전 교육과정 포맷(재량활동/특별활동) — 분석 미지원"):
        super().__init__(message)


class OcrError(Exception):
    """Vision OCR 페이지 호출이 재시도까지 소진하고 실패. 부분 출력은 하지 않는다.

    한 페이지라도 실패하면 레코드 누락 위험이 있어 문서 전체를 이 예외로 실패시킨다.
    호출측(워커)이 '일시성 OCR 실패 → 문서 단위 재시도/DLQ' 대상으로 판단하게 한다.
    """


class MissingSectionError(Exception):
    """필수 섹션 헤더(창체/교과/행특) 미검출 — OCR은 됐으나 생기부 구조가 아님.

    비(非)생기부·손상·미지원 구조라 재시도해도 같다(거절 대상). 일시성 OcrError(재시도)와
    구분하려 generic RuntimeError 대신 전용 예외로 둔다.
    """

