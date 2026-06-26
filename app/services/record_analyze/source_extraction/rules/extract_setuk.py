"""세부능력 및 특기사항(세특) 텍스트 기반 추출기.

입력:
  - output/{stem}.txt (페이지 사이 \\f, 행 사이 ' | ')
  - output/{stem}.json (페이지별 박스 좌표, 행간 갭 검출용)
  - section_split.py가 식별한 교과 페이지 범위
출력: {"세특": [{학년, 학기, 과목, 교과구분, 내용}, ...]}

알고리즘(상태 머신):
  - 학년 헤더 [N학년] 만나면 학년 전환, 교과구분 = "일반"으로 초기화
  - "<진로 선택 과목>" 헤더 → 교과구분 = "진로"
  - "<체육ㆍ예술…>" 헤더 → 교과구분 = "체육ㆍ예술"
  - "과목 | 세부능력 및 특기사항" 헤더 → 세특 영역 진입
  - "학기 | 교과 | 과목 | 단위수…" 헤더 / 이수단위 / 독서활동 → 세특 영역 종료
  - 세특 영역 안에서 "과목명 : 내용" 패턴 라인 = 새 레코드 시작
  - 세특 영역 안에서 빈 줄 신호(박스 좌표 cy 갭) 뒤에 ':' 없는 자유 문단이 시작되고
    "학교자율" 등 키워드가 포함되면 "학교자율교육과정탐구활동" 과목명으로 별도 레코드

후처리:
  - 내용 안에 "(1학기)"/"(2학기)" 표시가 함께 있으면 학기별로 별도 레코드 분리
  - 같은 학년에 동일 정규화 과목명("X I") 세특이 2개이면 두 번째를 "X II"로 보정
    (성적표 학기 마커가 OCR에서 자주 누락되어 dict 매칭 불가하므로 출현 순서로 가정)

규칙 출처: input/source_prompt/세특_prompt.txt
"""

import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .section_split import split_sections

DEFAULT_STEM = "고등학교생활기록부_서울대_김희선"
OUT_DIR = "output"
ROW_TOL = 0.6  # 같은 행 판단 기준 — ocr_paddle_table.py와 동일
GAP_FACTOR = 1.6  # 정상 행간 대비 이 배수 이상이면 빈 줄로 간주
MAX_GAP_PX = 200.0  # 이 이상의 갭은 페이지 본문 끝~푸터 사이로 보고 빈 줄로 삼지 않음
AUTONOMOUS_SUBJECT = "학교자율교육과정탐구활동"
# 학교자율 자유 문단 식별 키워드. 빈 줄 검출만으로는 잡음/푸터와 구분 불가하므로
# 텍스트 시작 부분에 키워드가 있을 때만 학교자율 레코드로 인정.
# 선택적 연도 prefix 허용: "2022 수업량유연화...", "2022학년도 학교자율..." 처럼
# 페이지 시작에서 연도로 시작하는 학교자율 활동 라인도 잡는다.
AUTONOMOUS_KEYWORDS = re.compile(
    r"(?:\d{4}\s*(?:학년도)?\s*)?"
    r"(?:학교\s*자율|수업량\s*유연화|자율\s*적?\s*교육\s*활동|학교\s*자율\s*과정)"
)
# 본문 텍스트에 등장하는 학교자율 활동 키워드(search용). 새마을운동 구술사처럼
# 본문 시작 키워드 매치가 안 되지만 본문 안에 학교자율 활동 표현이 있는 경우 잡는다.
# 'flush_autonomous'에서 페이지 사이 빈 줄로 누적된 buf 전체에 search.
AUTONOMOUS_BODY_KEYWORDS = re.compile(
    r"학교\s*자율|수업량\s*유연화|자율\s*적?\s*교육\s*활동|"
    r"교과\s*융합\s*(?:수업|활동|구술|형|학습|진로|프로그램)|"
    r"학교\s*자율\s*과정"
)


class 세특레코드(BaseModel):
    model_config = ConfigDict(frozen=True)
    학년: int = Field(..., ge=1, le=3)
    학기: int | None = None
    과목: str = Field(..., min_length=1)
    교과구분: str  # "일반" | "진로" | "체육ㆍ예술" | "일반(추가)" 등
    내용: str = Field(..., min_length=1)


class 세특결과(BaseModel):
    세특: list[세특레코드]


# 헤더 패턴 (OCR 변형 흡수: 글자 사이 공백 허용)
GRADE_HEADER_PAT = re.compile(r"\[\s*([123])\s*학\s*년\s*\]")
CAREER_HEADER_PAT = re.compile(r"<\s*진\s*로\s*선\s*택\s*과\s*목\s*>")
PE_ART_HEADER_PAT = re.compile(r"<\s*체\s*육\s*[ㆍ·\s]\s*예\s*술")
# 세특 진입 헤더 패턴:
#  - "과목 | 세부능력 및 특기사항" (일반 과목)
#  - "과목 | 특기사항"             (체육·예술 표 — "세부능력" 없이 짧은 헤더)
# OCR이 셀 경계를 잘못 잡아 "과목 | 세 | 부능력..." 처럼 한 글자 셀로 분리하는 케이스도 흡수.
SETUK_HEADER_PAT = re.compile(
    r"과\s*목\s*\|.*(?:세[\s|]*부[\s|]*능?\s*력|특\s*기\s*사\s*항)"
)
# 성적표 헤더: "학기 | 교과 | 과목 | 단위수 ..."
GRADE_TABLE_HEADER_PAT = re.compile(r"학\s*기\s*\|.*교\s*과\s*\|.*과\s*목\s*\|.*단\s*위\s*수")
# 페이지 푸터, 인쇄물 헤더.
# 학교명을 학교마다 일일이 추가하는 대신 학생부 표준 푸터에 공통으로 등장하는
# "반 | N | 번호" 패턴으로 학교명 무관하게 잡는다.
FOOTER_PAT = re.compile(
    r"문\s*서\s*확\s*인\s*번\s*호|정\s*부\s*24|본\s*증\s*명\s*서|"
    r"반\s*\|\s*\d+\s*\|\s*번\s*호"
)
# 페이지 헤더에 단독으로 잡히는 짧은 영숫자 워터마크 (예: "J10", "LO", "Ao", "HOR").
# 본문 라인에는 한글이 거의 항상 포함되므로 영숫자만 있는 짧은 라인은 잡음.
WATERMARK_PAT = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,3}$|^[A-Z0-9]{1,3}$")
# 이수단위 합계 (성적표 끝 표시)
UNIT_TOTAL_PAT = re.compile(r"이\s*수\s*단\s*위\s*합\s*계")
# 독서활동상황 (세특 종료)
READING_HEADER_PAT = re.compile(r"독\s*서\s*활\s*동\s*상\s*황|봉\s*사\s*활\s*동\s*실\s*적|행\s*동\s*특\s*성")

# "과목명 : 내용" 패턴. 라인 시작에 (1학기)/(2학기) 접두사가 올 수도 있음(통합과학 등).
# 과목명은 한글/영문/공백/특수문자(I, II, ㆍ, ·, 한자로마숫자, 숫자) 1~15자.
SUBJECT_LINE_PAT = re.compile(
    r"^\s*(?:\(\s*([12])\s*학\s*기\s*\)\s*)?"
    r"([가-힣A-Za-zⅠ-Ⅹⅰ-ⅹ](?:[\s·ㆍ가-힣A-Za-zIVXiⅠ-Ⅹⅰ-ⅹ0-9]{0,14})?)\s*:\s*(.+)$"
)

# 한자 로마숫자 → ASCII (프롬프트 규칙)
_ROMAN_MAP = str.maketrans({
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V",
    "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X",
    "ⅰ": "I", "ⅱ": "II", "ⅲ": "III", "ⅳ": "IV", "ⅴ": "V",
})


def _normalize_subject(name: str) -> str:
    """과목명 정규화: 한자 로마숫자 → ASCII, 한글+로마자 사이에 공백 1개,
    한글-한글 사이 공백 제거(매칭/dedup 일관성).

    Vision OCR은 '생활과 과학'처럼 과목명 내부에 공백을 넣지만 PaddleOCR은
    '생활과과학'으로 붙인다. 한글-한글 공백을 제거해 과목 동일성을 통일한다.
    """
    name = name.translate(_ROMAN_MAP)
    name = re.sub(r"([가-힣])([IVX]+)\b", r"\1 \2", name)
    name = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", name)
    return name.strip()


# (1학기) / (2학기) 분리 패턴
SEMESTER_TAG_PAT = re.compile(r"\(\s*([12])\s*학\s*기\s*\)")
# 직전 라인이 인용 따옴표가 닫히지 않은 채 끝났는지 — 다음 라인이 인용 본문의 연속이면
# 라인 시작 SUBJECT_LINE_PAT 매치(예: "분석:") 가 책 제목 인용 안의 콜론일 수 있다.
INCOMPLETE_QUOTE_END_PAT = re.compile(r"['\"`’][가-힣]{1,3}$")


def _cluster_rows_with_cy(
    boxes: list[dict], tol: float = ROW_TOL
) -> list[tuple[float, str]]:
    """박스 리스트를 행 단위로 묶고 (cy_평균, 행 텍스트) 리스트 반환.

    ocr_paddle_table.cluster_rows 와 동일한 알고리즘으로, 추가로 행의 cy 평균을 노출해
    인접 행 간 시각적 갭(빈 줄) 검출에 사용한다.
    """
    items = sorted(
        ((float(b["cy"]), float(b["x_left"]), float(b["h"]), str(b["text"])) for b in boxes),
        key=lambda i: (i[0], i[1]),
    )
    rows: list[tuple[float, str]] = []
    cur: list[tuple[float, str]] = []
    cur_y: float | None = None
    cur_h: float | None = None
    for cy, cx, h, t in items:
        if (
            cur
            and cur_y is not None
            and cur_h is not None
            and abs(cy - cur_y) <= max(cur_h, h) * tol
        ):
            cur.append((cx, t))
            cur_y = (cur_y * (len(cur) - 1) + cy) / len(cur)
            cur_h = max(cur_h, h)
        else:
            if cur and cur_y is not None:
                cur.sort()
                rows.append((cur_y, " | ".join(t for _, t in cur)))
            cur = [(cx, t)]
            cur_y = cy
            cur_h = h
    if cur and cur_y is not None:
        cur.sort()
        rows.append((cur_y, " | ".join(t for _, t in cur)))
    return rows


def _split_lines(
    text: str,
    page_ids: list[int],
    pages_json: list[dict] | None = None,
) -> list[str]:
    """교과 페이지의 모든 줄을 평탄화. pages_json이 주어지면 행 간 시각적 갭이 큰 곳에
    빈 줄("")을 삽입해 학기 마지막 자유 문단 분리 신호로 사용.
    """
    if pages_json is None:
        all_pages = text.split("\f")
        lines: list[str] = []
        for i in page_ids:
            page = all_pages[i - 1]
            for raw in page.split("\n"):
                line = raw.strip()
                if line:
                    lines.append(line)
        return lines

    pages_by_id = {p["page"]: p for p in pages_json}
    lines = []
    for page_idx, pid in enumerate(page_ids):
        # 페이지 시작 시 빈 줄을 한 개 삽입 (페이지 사이 셀 경계 신호로 사용).
        # 직전 페이지의 마지막 본문이 다음 페이지에서 다른 셀로 이어진다고 가정 — 같은 셀
        # 연속이면 _extract_records가 키워드 검사 후 직전 레코드에 다시 이어붙인다.
        if page_idx > 0 and lines and lines[-1] != "":
            lines.append("")
        page = pages_by_id.get(pid)
        if page is None:
            continue
        rows = _cluster_rows_with_cy(page["boxes"])
        if not rows:
            continue
        gaps = [rows[i + 1][0] - rows[i][0] for i in range(len(rows) - 1)]
        gap_threshold = float("inf")
        if gaps:
            sorted_gaps = sorted(gaps)
            median_gap = sorted_gaps[len(sorted_gaps) // 2]
            gap_threshold = median_gap * GAP_FACTOR
        for i, (cy, row_text) in enumerate(rows):
            stripped = row_text.strip()
            if stripped:
                lines.append(stripped)
            if i + 1 < len(rows):
                gap = rows[i + 1][0] - cy
                prev_text = row_text.strip()
                next_text = rows[i + 1][1].strip()
                # 직전 또는 직후 행이 푸터면 그 갭은 페이지 경계이므로 빈 줄로
                # 만들지 않는다 — 학기 갭과 cy 차이가 같은 케이스에서 본문 절단을 방지.
                prev_is_footer = bool(FOOTER_PAT.search(prev_text))
                next_is_footer = bool(FOOTER_PAT.search(next_text))
                if (
                    gap_threshold < gap < MAX_GAP_PX
                    and not (prev_is_footer or next_is_footer)
                    and lines
                    and lines[-1] != ""
                ):
                    lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _last_semester_in_year(records: list[dict], 학년: int) -> int | None:
    """현재 학년의 직전 레코드에서 학기 정보를 추정.
    레코드의 학기 필드 또는 본문 안의 마지막 (N학기) 태그를 사용.
    """
    for r in reversed(records):
        if r["학년"] != 학년:
            return None
        if r["학기"]:
            return r["학기"]
        tags = SEMESTER_TAG_PAT.findall(r["내용"])
        if tags:
            return int(tags[-1])
    return None


def _extract_records(lines: list[str]) -> list[dict]:
    """라인 리스트를 상태 머신으로 처리해 세특 레코드 리스트 반환.

    학교자율 레코드 분리는 두 신호 사용:
      1) 라인이 '학교자율'/'수업량 유연화' 등 키워드로 *시작*하면 즉시 새 레코드.
      2) 빈 줄 신호(_split_lines가 cy 갭 기반으로 삽입) 뒤에 ':' 없는 자유 문단을
         autonomous_buf에 누적, 본문 안에 키워드가 있으면 학교자율 레코드로 분리.
    페이지 본문 끝~푸터 사이의 큰 갭은 _split_lines의 MAX_GAP_PX로 빈 줄에서 제외돼
    페이지 경계로 인한 본문 절단을 막는다.
    """
    records: list[dict] = []
    current: dict | None = None
    autonomous_buf: list[str] = []

    학년 = 1
    교과구분 = "일반"
    in_setuk = False
    # 직전 *세특 본문* 라인 — 인용 미완성 종결을 다음 라인의 SUBJECT 매치 가드로 사용.
    prev_body_line: str = ""

    def flush_current() -> None:
        nonlocal current
        if current and current["내용"].strip():
            records.append(current)
        current = None

    def _append_to_prev_record(text: str) -> None:
        for r in reversed(records):
            if r["학년"] == 학년 and r["교과구분"] == 교과구분:
                r["내용"] += " " + text
                return

    def flush_autonomous() -> None:
        nonlocal autonomous_buf
        if not autonomous_buf:
            return
        buf = autonomous_buf
        autonomous_buf = []

        # 라인 단위로 학교자율 키워드 첫 등장 위치 탐색.
        # 매치 라인 앞쪽 본문은 직전 페이지 과목 본문의 연속으로 보고 직전 레코드에 이어붙이고,
        # 매치 라인부터 끝까지는 학교자율 레코드로 만든다. 어윤서 일본어회화 I 본문 연속 +
        # 학교자율 활동(해자결지 교과융합 수업)이 한 페이지에 같이 있는 케이스 대응.
        keyword_idx = None
        for i, line in enumerate(buf):
            if AUTONOMOUS_BODY_KEYWORDS.search(line):
                keyword_idx = i
                break

        if keyword_idx is None:
            # 키워드 없음 — 모두 직전 레코드에 이어붙임 (페이지 경계 본문 절단 방지)
            text = " ".join(buf).strip()
            if text:
                _append_to_prev_record(text)
            return

        before_text = " ".join(buf[:keyword_idx]).strip()
        after_text = " ".join(buf[keyword_idx:]).strip()
        if before_text:
            _append_to_prev_record(before_text)
        if after_text:
            records.append({
                "학년": 학년,
                "학기": _last_semester_in_year(records, 학년),
                "과목": AUTONOMOUS_SUBJECT,
                "교과구분": 교과구분,
                "내용": after_text,
            })

    for line in lines:
        if line == "":
            if in_setuk:
                flush_current()
            continue

        if FOOTER_PAT.search(line):
            continue
        if WATERMARK_PAT.match(line):
            continue

        if m := GRADE_HEADER_PAT.search(line):
            flush_autonomous()
            flush_current()
            학년 = int(m.group(1))
            교과구분 = "일반"
            in_setuk = False
            continue

        if CAREER_HEADER_PAT.search(line):
            flush_autonomous()
            flush_current()
            교과구분 = "진로"
            in_setuk = False
            continue
        if PE_ART_HEADER_PAT.search(line):
            flush_autonomous()
            flush_current()
            교과구분 = "체육ㆍ예술"
            in_setuk = False
            continue

        if SETUK_HEADER_PAT.search(line):
            in_setuk = True
            continue

        if GRADE_TABLE_HEADER_PAT.search(line) or UNIT_TOTAL_PAT.search(line):
            flush_autonomous()
            flush_current()
            in_setuk = False
            continue
        if READING_HEADER_PAT.search(line):
            flush_autonomous()
            flush_current()
            in_setuk = False
            continue

        if not in_setuk:
            continue

        # 학교자율 키워드로 시작하는 라인 = 새 학교자율 레코드 즉시 시작
        if AUTONOMOUS_KEYWORDS.match(line):
            flush_autonomous()
            flush_current()
            current = {
                "학년": 학년,
                "학기": _last_semester_in_year(records, 학년),
                "과목": AUTONOMOUS_SUBJECT,
                "교과구분": 교과구분,
                "내용": line,
            }
            prev_body_line = line
            continue

        m = SUBJECT_LINE_PAT.match(line)
        # 직전 본문 라인이 인용 미완성으로 끝났으면 라인 시작 SUBJECT 매치(콜론)는
        # 책 제목 인용 안의 콜론일 수 있으니 새 레코드로 보지 않고 현재 본문에 이어붙임.
        if m and ":" in line and not INCOMPLETE_QUOTE_END_PAT.search(prev_body_line):
            flush_autonomous()
            sem_str = m.group(1)
            과목 = _normalize_subject(m.group(2))
            내용 = m.group(3).strip()
            if not 과목 or len(과목) > 15:
                if current:
                    current["내용"] += " " + line
                prev_body_line = line
                continue
            flush_current()
            current = {
                "학년": 학년,
                "학기": int(sem_str) if sem_str else None,
                "과목": 과목,
                "교과구분": 교과구분,
                "내용": 내용,
            }
        else:
            if current is None:
                autonomous_buf.append(line)
            else:
                current["내용"] += " " + line
        prev_body_line = line

    flush_autonomous()
    flush_current()
    return records


# 내용 안에 끼어든 "(N학기)과목명:" 경계. Vision OCR이 1·2학기 세특을 한 문단으로
# 합치는 케이스에서 학기별로 다시 분리하기 위한 패턴. 과목명은 SUBJECT_LINE_PAT과
# 동일한 문자 집합을 쓰되 콜론까지 포함해 본문 중 우연한 학기 태그와 구분한다.
INLINE_SUBJECT_TAG_PAT = re.compile(
    r"\(\s*([12])\s*학\s*기\s*\)\s*"
    r"([가-힣A-Za-zⅠ-Ⅹⅰ-ⅹ](?:[\s·ㆍ가-힣A-Za-zIVXiⅠ-Ⅹⅰ-ⅹ0-9]{0,14})?)\s*:"
)


def _split_semesters(records: list[dict]) -> list[dict]:
    """내용에 (1학기)/(2학기) 표시가 함께 있으면 학기별로 분리.

    두 가지 케이스:
      1) 본문 안에 (1학기).../(2학기)... 가 둘 다 등장 → 태그 기준으로 분리.
      2) 레코드 학기(선두 태그가 SUBJECT_LINE_PAT으로 이미 소비됨) + 본문 안에
         "(N학기)과목:" 경계가 끼어 있음 → Vision 문단 병합. 경계에서 새 레코드 분리.
    """
    out: list[dict] = []
    for r in records:
        text = r["내용"]

        inline = list(INLINE_SUBJECT_TAG_PAT.finditer(text))
        if inline and r["학기"] is not None:
            cursor = 0
            cur_sem = r["학기"]
            cur_subj = r["과목"]
            for m in inline:
                seg = text[cursor:m.start()].strip()
                if seg:
                    out.append({**r, "학기": cur_sem, "과목": cur_subj, "내용": seg})
                cur_sem = int(m.group(1))
                cur_subj = _normalize_subject(m.group(2))
                cursor = m.end()
            tail = text[cursor:].strip()
            if tail:
                out.append({**r, "학기": cur_sem, "과목": cur_subj, "내용": tail})
            continue

        tags = SEMESTER_TAG_PAT.findall(text)
        if len(set(tags)) < 2:
            if tags:
                r["학기"] = int(tags[0])
            out.append(r)
            continue
        parts: list[tuple[int, str]] = []
        cursor = 0
        last_sem: int | None = None
        for m in SEMESTER_TAG_PAT.finditer(text):
            if last_sem is not None:
                parts.append((last_sem, text[cursor:m.start()].strip()))
            cursor = m.end()
            last_sem = int(m.group(1))
        if last_sem is not None:
            parts.append((last_sem, text[cursor:].strip()))
        for sem, content in parts:
            if content:
                out.append({**r, "학기": sem, "내용": content})
    return out


def _correct_duplicate_roman_subject(records: list[dict]) -> list[dict]:
    """같은 학년에 정규화 과목명이 정확히 동일한 세특이 2개이고 둘 다 'X I' 형식이면,
    OCR이 'X II'를 'X I'로 잘못 인식했다고 보고 두 번째 레코드를 'X II'로 교체한다.

    근거: 성적표 학기 마커가 OCR에서 자주 누락되어 학기별 dict 매칭이 불가능하지만,
    같은 학년에 동일 과목이 두 번 등장하는 자체가 비정상(보통 학기별 I/II). 출현 순서로
    1학기 → 2학기 가정.
    """
    by_year_subj: dict[tuple[int, str], list[int]] = {}
    for i, r in enumerate(records):
        by_year_subj.setdefault((r["학년"], r["과목"]), []).append(i)

    for (_, subj), idxs in by_year_subj.items():
        if len(idxs) != 2:
            continue
        parts = subj.rsplit(" ", 1)
        if len(parts) != 2 or parts[1] != "I":
            continue
        base = parts[0]
        first, second = idxs
        if records[first]["학기"] is None:
            records[first]["학기"] = 1
        records[second]["과목"] = f"{base} II"
        records[second]["학기"] = 2
    return records


def extract(
    text: str,
    교과_page_ids: list[int],
    pages_json: list[dict] | None = None,
) -> 세특결과:
    lines = _split_lines(text, 교과_page_ids, pages_json)
    raw = _extract_records(lines)
    final = _split_semesters(raw)
    final = _correct_duplicate_roman_subject(final)
    return 세특결과(세특=[세특레코드(**r) for r in final])


def main() -> None:
    stem = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STEM
    txt_path = Path(OUT_DIR) / f"{stem}.txt"
    json_path = Path(OUT_DIR) / f"{stem}.json"
    text = txt_path.read_text(encoding="utf-8")
    pages_json = None
    if json_path.exists():
        with json_path.open(encoding="utf-8") as f:
            pages_json = json.load(f)
    sections = split_sections(text)
    result = extract(text, sections["교과"], pages_json)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
