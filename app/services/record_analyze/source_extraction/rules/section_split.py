"""학교생활기록부 OCR 텍스트에서 세 섹션(창체/교과/행특)의 페이지 범위를 분리한다.

입력: ocr_paddle_table_result.txt (페이지 사이 form-feed `\\f` 구분).
출력: {"창체": [...], "교과": [...], "행특": [...]} — 각 섹션이 차지하는 1-based 페이지 번호 배열.

분리 규칙은 input/source_prompt/page_seperate_prompt.txt 사양을 OCR 텍스트 기반으로 재현:
  - 창체: '창의적 체험활동상황' 첫 등장 ~ '봉사활동실적' 직전 (같은 페이지면 그 페이지 포함)
  - 교과: '교과학습발달상황' 첫 등장 ~ '독서활동상황' 직전 (없으면 '행동특성 및 종합의견' 직전)
  - 행특: '행동특성 및 종합의견' 첫 등장 ~ PDF 끝
OCR 띄어쓰기 변형(글자 사이 공백)을 견디기 위해 정규식은 글자 사이에 `\\s*`를 허용한다.

차단 키워드(봉사/독서)가 페이지 **상단**에 있으면 별도 페이지(직전까지 종료),
**중간 이후**면 같은 페이지에서 시작(그 페이지 포함). 한 페이지가 두 섹션에 걸치면
양쪽 모두에 포함시켜, 후속 추출기가 자기 섹션 헤더 기준으로 자기 영역만 읽도록 한다.
"""

import re


class UnsupportedRecordFormatError(Exception):
    """분석 미지원 생기부 포맷 신호 — 호출측이 분석을 건너뛰고 거절(reject)하도록.

    예: 2011 개정 이전 교육과정('창의적 재량활동상황'+'특별활동상황'). OCR/파서 결함에
    의한 일반 추출 실패(RuntimeError)와 구분해, '미지원 포맷'으로 의도적 거절할 때 쓴다.
    """


def _spaced(s: str) -> re.Pattern:
    """글자 사이에 공백이 들어가도 매칭되도록 패턴화."""
    return re.compile(r"\s*".join(re.escape(c) for c in s))


PATTERNS = {
    "창체": _spaced("창의적체험활동상황"),
    "교과": _spaced("교과학습발달상황"),
    "행특": _spaced("행동특성및종합의견"),
    "독서": _spaced("독서활동상황"),
    "봉사": _spaced("봉사활동실적"),
    "재량": _spaced("재량활동상황"),
    "특별활동": _spaced("특별활동상황"),
}


def _find_first(pages: list[str], pattern: re.Pattern, start: int = 1) -> int | None:
    """1-based 페이지 번호로 첫 매칭 페이지 반환. start 이전 페이지는 무시."""
    for i, page in enumerate(pages, start=1):
        if i < start:
            continue
        if pattern.search(page):
            return i
    return None


# 차단 키워드 매칭이 페이지 본문의 이 비율보다 앞에 있으면 '해당 페이지에서 새 섹션이 단독으로 시작'.
# 그 이후면 '같은 페이지에 이전 섹션 본문과 새 섹션이 공존'으로 본다.
_TOP_THRESHOLD = 0.3


def _starts_alone(page: str, pattern: re.Pattern) -> bool:
    m = pattern.search(page)
    if not m or not page:
        return False
    return m.start() <= len(page) * _TOP_THRESHOLD


def _section_end(blocker_start: int | None, blocker_pat: re.Pattern, pages: list[str], fallback_end: int) -> int:
    """차단 키워드 페이지를 기준으로 섹션 종료 페이지(1-based, 포함) 결정."""
    if blocker_start is None:
        return fallback_end
    if _starts_alone(pages[blocker_start - 1], blocker_pat):
        return blocker_start - 1
    return blocker_start  # 같은 페이지에 공존 → 그 페이지까지 포함


LEGACY_FORMAT_MESSAGE = "2011 개정 이전 교육과정 포맷(재량활동/특별활동) — 분석 미지원"


def is_legacy_format(text: str) -> bool:
    """2011 개정 이전 옛 교육과정 포맷 여부.

    현대 창체 헤더(창의적체험활동상황)가 없고 옛 헤더(재량활동상황/특별활동상황)가
    양성으로 잡히면 옛 포맷. '헤더 부재'만으로 단정하지 않아(텍스트 레이어 없는 스캔본
    현대 문서를 오거절하지 않음) PDF 내장 텍스트·OCR 텍스트 어느 쪽에도 동일하게 쓴다.
    """
    pages = text.split("\f")
    if _find_first(pages, PATTERNS["창체"]):
        return False
    return bool(_find_first(pages, PATTERNS["재량"]) or _find_first(pages, PATTERNS["특별활동"]))


def split_sections(text: str) -> dict[str, list[int]]:
    pages = text.split("\f")
    total = len(pages)

    s_창체 = _find_first(pages, PATTERNS["창체"])
    s_교과 = _find_first(pages, PATTERNS["교과"])
    s_행특 = _find_first(pages, PATTERNS["행특"])

    if is_legacy_format(text):
        raise UnsupportedRecordFormatError(LEGACY_FORMAT_MESSAGE)

    if s_창체 is None or s_교과 is None or s_행특 is None:
        raise RuntimeError(f"필수 섹션 헤더 매칭 실패: 창체={s_창체}, 교과={s_교과}, 행특={s_행특}")

    s_봉사 = _find_first(pages, PATTERNS["봉사"], start=s_창체)
    s_독서 = _find_first(pages, PATTERNS["독서"], start=s_교과)

    e_창체 = _section_end(s_봉사, PATTERNS["봉사"], pages, fallback_end=s_교과 - 1)
    # 교과 종료: 독서활동상황을 우선 차단 키워드로 사용. 없으면(일부 PDF는 9번 영역 자체가
    # 비어있어 OCR에 안 잡힘) 행특 헤더 위치로 결정 — 행특이 페이지 중간 이후에 등장하면
    # 그 페이지에도 세특 본문이 같이 있으니 교과에 포함시킨다.
    if s_독서 is not None:
        e_교과 = _section_end(s_독서, PATTERNS["독서"], pages, fallback_end=s_행특 - 1)
    else:
        e_교과 = _section_end(s_행특, PATTERNS["행특"], pages, fallback_end=s_행특 - 1)
    e_행특 = total  # 행특 이후 페이지에 다른 섹션 없음(증명 페이지만 따라옴)

    return {
        "창체": list(range(s_창체, e_창체 + 1)),
        "교과": list(range(s_교과, e_교과 + 1)),
        "행특": list(range(s_행특, e_행특 + 1)),
    }
