"""행동특성 및 종합의견(행특) 좌표 기반 추출기.

입력:
  - ocr_paddle_table_result.json (박스 좌표 포함 OCR 결과)
  - section_split.py가 식별한 행특 페이지 범위(텍스트 기반)
출력: {"행특": [{"학년": int, "내용": str}, ...]}

핵심 알고리즘 — 학년 마커는 셀의 세로 중앙에 위치하므로 마커 cy 자체가 아니라
인접 마커들의 cy 중간점을 셀 경계로 본다. 한 학년 셀이 페이지 경계를 넘는 경우,
이전 페이지 마지막 학년(prev_grade)을 다음 페이지로 전파한다.

규칙 출처: input/source_prompt/행특_prompt.txt
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

# 좌측 학년 마커 식별 임계값: x_left < page_width * 이 비율
# (행특 표의 학년 컬럼은 페이지 좌측 ~16% 영역에 위치)
GRADE_MARKER_X_RATIO = 0.20
# 상/하단 인쇄물 헤더·푸터 영역(이 비율 안의 박스는 본문에서 제외)
# (생기부 푸터 "청주대성고등학교 | YYYY년..."는 페이지 ~79% 위치)
TOP_MARGIN_RATIO = 0.07
BOTTOM_MARGIN_RATIO = 0.77
# 셀 경계 검출: 인접 박스의 cy 갭이 이 픽셀 이상이면 새 셀로 분리.
# 200dpi 기준 정상 행 간격은 ~32-35px, 셀 사이 갭은 ~41-43px. 38이면 안전한 임계.
# 마커 위치(셀 중앙/위쪽/하단)와 무관하게 동작하므로 PDF 종류 불문 견고.
CELL_GAP_THRESHOLD = 38
# 워터마크 식별: 본문 박스는 좌측 정렬(x_left ≈ 페이지 너비×0.20)이고, "열람용" 같은
# 워터마크 글자는 페이지 중앙·우측에 흩어져 있으며 한 박스에 한 글자만 들어가 width가 작다.
# x_left가 본문 정렬 영역 밖(>0.25)이고 width가 작으면(<0.20) 워터마크로 간주.
WATERMARK_MIN_WIDTH_RATIO = 0.20
WATERMARK_LEFT_RATIO = 0.25


class 행특레코드(BaseModel):
    model_config = ConfigDict(frozen=True)
    학년: int = Field(..., ge=1, le=3)
    내용: str = Field(..., min_length=1)


class 행특결과(BaseModel):
    행특: list[행특레코드]


# OCR 띄어쓰기 변형 허용 패턴
def _spaced(s: str) -> re.Pattern:
    return re.compile(r"\s*".join(re.escape(c) for c in s))


HEADER_PAT = _spaced("행동특성및종합의견")
COL_HEADER_PAT = re.compile(r"^\s*학\s*년\s*\|?.*행\s*동")  # "학년 | 행동특성..." 형태
PRINT_HEADER_PAT = re.compile(r"문\s*서\s*확\s*인\s*번\s*호|정\s*부\s*24")
END_PAGE_PAT = re.compile(r"발\s*급\s*번\s*호|사\s*본\s*임\s*을|위\s*사\s*람\s*의\s*학\s*교\s*생\s*활")
GRADE_TEXT_PAT = re.compile(r"^\s*([123])\s*$")
# 단독 "학년" 박스(컬럼 헤더 일부), 또는 표 헤더 단편
COL_HEADER_TOKEN_PAT = re.compile(r"^\s*(학\s*년|행\s*동\s*특\s*성|종\s*합\s*의\s*견|특\s*기\s*사\s*항|독\s*서\s*활\s*동\s*상\s*황|과\s*목)\s*$")


@dataclass(frozen=True)
class _Marker:
    학년: int
    cy: float


def _is_footer(text: str) -> bool:
    return bool(re.search(r"\d{4}\s*년.*\d+\s*/\s*\d+", text))


def _is_noise(text: str) -> bool:
    """짧은 OCR 잡음('J1', 'Ao', 'o' 등 한글 없는 2자 이하)."""
    return len(text) <= 2 and not any("가" <= c <= "힣" for c in text)


def _body_boxes_of_page(page: dict, is_first: bool) -> list[dict]:
    """본문 박스: 인쇄물 헤더·푸터·표 컬럼 헤더·행특 헤더 자체·OCR 잡음 제외."""
    boxes = page["boxes"]
    width = page["width"]
    height = page["height"]
    top_y = height * TOP_MARGIN_RATIO
    bottom_y = height * BOTTOM_MARGIN_RATIO

    # 첫 페이지면 행특 헤더 cy를 본문 시작점으로
    body_y_start = 0.0
    if is_first:
        for b in boxes:
            if HEADER_PAT.search(b["text"]):
                body_y_start = b["y_bottom"]
                break

    out: list[dict] = []
    for b in boxes:
        t = b["text"].strip()
        if not t:
            continue
        if b["cy"] < max(body_y_start, top_y):
            continue  # 행특 헤더 이전 또는 인쇄물 상단 영역
        if b["cy"] > bottom_y:
            continue  # 페이지 푸터 영역
        # 학년 마커("1"/"2"/"3" + 좌측 영역)는 잡음/짧은 텍스트 필터를 우회
        is_grade_marker = bool(GRADE_TEXT_PAT.match(t)) and b["x_left"] < width * GRADE_MARKER_X_RATIO
        if is_grade_marker:
            out.append({**b, "page": page["page"]})
            continue
        if PRINT_HEADER_PAT.search(t) or _is_footer(t):
            continue
        if HEADER_PAT.search(t) or COL_HEADER_PAT.search(t) or COL_HEADER_TOKEN_PAT.match(t):
            continue
        if _is_noise(t):
            continue
        # 워터마크("열람용" 등): x_left가 본문 정렬 영역 밖이고 박스 너비가 작음
        if b["x_left"] > width * WATERMARK_LEFT_RATIO and b["w"] < width * WATERMARK_MIN_WIDTH_RATIO:
            continue
        out.append({**b, "page": page["page"]})
    return out


def _markers_and_remove(body_boxes: list[dict], page_width: int) -> tuple[list[_Marker], list[dict]]:
    """좌측 영역의 학년 숫자 박스를 마커로 식별하고, 본문 박스에서 마커 박스를 제거."""
    threshold = page_width * GRADE_MARKER_X_RATIO
    markers: list[_Marker] = []
    rest: list[dict] = []
    for b in body_boxes:
        m = GRADE_TEXT_PAT.match(b["text"])
        if m and b["x_left"] < threshold:
            markers.append(_Marker(학년=int(m.group(1)), cy=b["cy"]))
        else:
            rest.append(b)
    return sorted(markers, key=lambda m: m.cy), rest


def _assign_grades(body_boxes: list[dict], markers: list[_Marker], prev_grade: int) -> dict[int, list[dict]]:
    """본문 박스를 학년에 할당.

    알고리즘:
      1) 본문 박스를 cy 순서로 정렬
      2) 인접 박스의 cy 갭이 CELL_GAP_THRESHOLD 이상이면 새 셀 그룹으로 분리
      3) 학년 마커 cy가 어느 그룹의 영역(인접 그룹 사이 중간점 기준)에 속하는지로
         그 그룹의 학년을 결정
      4) 마커 없는 그룹은 직전 학년(또는 페이지 진입 시 prev_grade)로 채움
    """
    out: dict[int, list[dict]] = {}
    if not body_boxes:
        return out

    sorted_boxes = sorted(body_boxes, key=lambda b: b["cy"])

    # 갭 기반 셀 그룹화
    groups: list[list[dict]] = [[sorted_boxes[0]]]
    for prev_b, curr_b in zip(sorted_boxes, sorted_boxes[1:]):
        if curr_b["cy"] - prev_b["cy"] > CELL_GAP_THRESHOLD:
            groups.append([])
        groups[-1].append(curr_b)

    # 그룹 사이 셀 경계(중간점)
    boundaries: list[float] = []
    for i in range(len(groups) - 1):
        last_cy = groups[i][-1]["cy"]
        first_cy = groups[i + 1][0]["cy"]
        boundaries.append((last_cy + first_cy) / 2)

    # 각 그룹의 학년 결정
    group_grades: list[int | None] = [None] * len(groups)
    for m in markers:
        idx = 0
        for bnd in boundaries:
            if m.cy < bnd:
                break
            idx += 1
        if 0 <= idx < len(groups):
            group_grades[idx] = m.학년

    # 마커 없는 그룹은 직전 학년으로(첫 그룹이면 prev_grade)
    current = prev_grade
    for i in range(len(groups)):
        if group_grades[i] is None:
            group_grades[i] = current
        current = group_grades[i]

    for grade, group in zip(group_grades, groups):
        if grade is not None:
            out.setdefault(grade, []).extend(group)
    return out


def _boxes_to_text(boxes: list[dict]) -> str:
    """박스 리스트를 (페이지, cy, x_left) 순으로 정렬해 공백으로 join."""
    boxes = sorted(boxes, key=lambda b: (b.get("page", 0), b["cy"], b["x_left"]))
    return " ".join(b["text"].strip() for b in boxes if b["text"].strip())


def extract(pages_json: list[dict], 행특_page_ids: list[int]) -> 행특결과:
    haengtuk_pages = [p for p in pages_json if p["page"] in 행특_page_ids]
    haengtuk_pages.sort(key=lambda p: p["page"])

    grade_boxes: dict[int, list[dict]] = {}
    prev_grade = 1  # 행특은 학년 1부터 시작
    first = True
    for page in haengtuk_pages:
        page_text = " ".join(b["text"] for b in page["boxes"])
        if END_PAGE_PAT.search(page_text):
            break  # 증명 페이지 도달

        body_boxes = _body_boxes_of_page(page, is_first=first)
        first = False
        if not body_boxes:
            continue

        markers, body_for_text = _markers_and_remove(body_boxes, page["width"])
        grade_to_boxes = _assign_grades(body_for_text, markers, prev_grade)
        for g, bxs in grade_to_boxes.items():
            grade_boxes.setdefault(g, []).extend(bxs)

        if markers:
            prev_grade = markers[-1].학년

    records = [
        행특레코드(학년=g, 내용=_boxes_to_text(grade_boxes[g]))
        for g in sorted(grade_boxes)
        if _boxes_to_text(grade_boxes[g])
    ]
    return 행특결과(행특=records)