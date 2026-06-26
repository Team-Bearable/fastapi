"""창의적 체험활동상황(창체) 좌표 기반 추출기.

입력:
  - output/{stem}.json (박스 좌표 포함 OCR 결과)
  - output/{stem}.txt (섹션 분리용)
출력: {"창체": [{"학년", "영역", "시간", "희망분야", "특기사항"}, ...]}

표 구조: 학년 | 영역 | 시간 | 특기사항
  - 학년 컬럼: x_left ratio ~0.15-0.19
  - 영역 컬럼: ~0.22 (자율활동/동아리활동/진로활동/봉사활동)
  - 시간 컬럼: ~0.26-0.36 (숫자, 영역 마커와 같은 cy)
  - 특기사항 컬럼: ~0.36+ (긴 본문)

알고리즘:
  1) 박스를 컬럼별로 분류(학년/영역/시간/본문)
  2) 영역 마커 cy로 영역 셀 경계 결정 (첫 마커 위쪽도 그 영역에 포함 — 셀 안 위쪽 줄)
  3) 본문 박스를 영역 cy 범위에 할당. 페이지 넘김 시 prev_area로 이전 영역 연속
  4) 학년 마커 cy로 영역에 학년 매핑. 마커 없는 영역은 prev_grade
  5) 시간 마커 cy로 영역에 시간 매핑 (영역 마커와 같은 cy)
  6) 봉사활동 제외, 진로활동의 "희망분야: ..." 분리

규칙 출처: input/source_prompt/창체_prompt.txt
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .section_split import split_sections

DEFAULT_STEM = "고등학교생활기록부_서울대_김희선"
OUT_DIR = "output"

# 컬럼 x_left 비율
GRADE_X_MAX = 0.20
AREA_X_MIN = 0.20
AREA_X_MAX = 0.30
TIME_X_MIN = 0.25
TIME_X_MAX = 0.40
BODY_X_MIN = 0.30
# 본문 영역 (페이지 상하 마진)
TOP_MARGIN_RATIO = 0.07
BOTTOM_MARGIN_RATIO = 0.77

ALLOWED_AREAS = ("자율활동", "동아리활동", "진로활동")
EXCLUDED_AREAS = ("봉사활동",)


class 창체레코드(BaseModel):
    model_config = ConfigDict(frozen=True)
    학년: int = Field(..., ge=1, le=3)
    영역: str  # 자율활동 | 동아리활동 | 진로활동
    시간: int | None = None
    희망분야: str | None = None
    특기사항: str = Field(..., min_length=1)


class 창체결과(BaseModel):
    창체: list[창체레코드]


# 패턴
GRADE_TEXT_PAT = re.compile(r"^\s*([123])\s*$")
AREA_TEXT_PAT = re.compile(r"^\s*(자\s*율\s*활\s*동|동\s*아\s*리\s*활\s*동|진\s*로\s*활\s*동|봉\s*사\s*활\s*동)\s*$")
NUM_PAT = re.compile(r"^\s*(\d+)\s*$")
HEADER_PAT = re.compile(r"창\s*의\s*적\s*체\s*험\s*활\s*동\s*상\s*황")
COL_HEADER_TOKEN_PAT = re.compile(r"^\s*(학\s*년|영\s*역|시\s*간|특\s*기\s*사\s*항)\s*$")
PRINT_HEADER_PAT = re.compile(r"문\s*서\s*확\s*인\s*번\s*호|정\s*부\s*24")
FOOTER_PAT = re.compile(r"\d{4}\s*년.*\d+\s*/\s*\d+")
# 봉사활동실적 표 헤더 — OCR이 "봉사 활 동 실 적" 처럼 글자 사이 공백을 넣어 인식할 수 있어 공백 허용 정규식.
BONGSA_HEADER_PAT = re.compile(r"봉\s*사\s*활\s*동\s*실\s*적")
# 희망분야: "희망분야 | 교육분야" 또는 "희망분야: 교육분야" 또는 "희망분야 교육분야"
DESIRED_FIELD_PAT = re.compile(r"희\s*망\s*분\s*야\s*[:|│｜]?\s*(.+)")
# '희망분야' 단독 행 (값이 비어있는 케이스). 박스는 제거하되 희망분야 값은 None.
DESIRED_FIELD_EMPTY_PAT = re.compile(r"^\s*희\s*망\s*분\s*야\s*[:|│｜]?\s*$")
# 워터마크 식별 (extract_haengtuk와 동일)
WATERMARK_MIN_WIDTH_RATIO = 0.20
WATERMARK_LEFT_RATIO = 0.25


@dataclass(frozen=True)
class _Marker:
    cy: float
    kind: str  # 'grade' | 'area' | 'time'
    value: object  # int(학년/시간) or str(영역)


def _classify_box(b: dict, width: int) -> tuple[str, object] | None:
    """박스를 컬럼별 분류. (kind, value) 또는 None(노이즈)."""
    t = b["text"].strip()
    if not t:
        return None
    xL = b["x_left"] / width
    # 학년 마커
    if xL < GRADE_X_MAX and (m := GRADE_TEXT_PAT.match(t)):
        return ("grade", int(m.group(1)))
    # 영역 마커
    if AREA_X_MIN <= xL < AREA_X_MAX and (m := AREA_TEXT_PAT.match(t)):
        return ("area", re.sub(r"\s+", "", m.group(1)))
    # 시간 마커 (영역 컬럼 다음 좁은 컬럼)
    if TIME_X_MIN <= xL < TIME_X_MAX and (m := NUM_PAT.match(t)):
        return ("time", int(m.group(1)))
    # 본문 — len>=2 허용: 희망분야 값이 '국제', '의학' 같은 2글자 단어인 케이스 포용.
    # 1글자는 워터마크/페이지 번호 등 OCR 노이즈일 가능성이 높아 제외 유지.
    if xL >= BODY_X_MIN and len(t) >= 2:
        return ("body", t)
    return None


def _is_noise_or_header(t: str) -> bool:
    if PRINT_HEADER_PAT.search(t):
        return True
    if FOOTER_PAT.search(t):
        return True
    if HEADER_PAT.search(t):
        return True
    if COL_HEADER_TOKEN_PAT.match(t):
        return True
    return False


def _collect_markers_and_body(page: dict) -> tuple[list[_Marker], list[dict]]:
    """페이지의 마커(학년/영역/시간)와 본문 박스를 추출.

    페이지에 '창의적 체험활동상황' 헤더 박스가 있으면 그 박스 y_bottom 이후만 본문으로
    사용한다 — 창체 시작 페이지 위쪽에 자격증/국가직무능력표준 같은 다른 섹션 내용이
    같이 있어 본문에 잔재로 섞이는 것을 막는다.
    """
    width = page["width"]
    height = page["height"]
    top_y = height * TOP_MARGIN_RATIO
    bot_y = height * BOTTOM_MARGIN_RATIO

    # 창체 헤더 박스 (여러 개면 가장 큰 y_bottom 사용)
    body_y_start = top_y
    for b in page["boxes"]:
        if HEADER_PAT.search(b["text"]):
            body_y_start = max(body_y_start, b["y_bottom"])

    # 봉사활동실적 표는 창체 마지막에 별도 표로 등장 — 그 위쪽까지만 본문으로 사용.
    # 그렇지 않으면 봉사활동실적 표 본문이 직전 진로활동 영역에 잘못 흡수된다.
    # OCR이 "봉사 활 동 실 적" 처럼 글자 사이 공백을 넣어 인식하는 케이스도 흡수.
    for b in page["boxes"]:
        if BONGSA_HEADER_PAT.search(b["text"]):
            bot_y = min(bot_y, b["y_top"])

    markers: list[_Marker] = []
    body: list[dict] = []
    for b in page["boxes"]:
        t = b["text"].strip()
        if not t:
            continue
        if b["cy"] <= body_y_start or b["cy"] >= bot_y:
            continue
        if _is_noise_or_header(t):
            continue
        cls = _classify_box(b, width)
        if cls is None:
            continue  # 마커도 본문도 아님 (한두 글자 워터마크 등이 여기서 자동 제외 — len>=3 조건)
        kind, value = cls
        if kind == "body":
            body.append({**b, "page": page["page"]})
        else:
            markers.append(_Marker(cy=b["cy"], kind=kind, value=value))
    return markers, body


def _adjust_career_marker(area_markers: list[_Marker], body_boxes: list[dict]) -> list[_Marker]:
    """진로활동 마커 cy를 그 위쪽 '희망분야' 박스 cy로 조정.

    OCR이 진로활동 마커를 셀 중앙·하단에 잡는 경우, 셀 첫 줄인 '희망분야' 행이
    마커 위쪽에 있어 이전 영역으로 잘못 분류된다. 마커 cy를 희망분야 cy로 끌어올려
    셀 시작 위치를 정확히 만든다. 진로활동 외 다른 영역 마커는 cy 그대로 유지.

    -5px 마진을 두는 이유: 희망분야 행의 박스들이 미세하게 다른 cy(예: 544, 542)로
    잡혀, 마커 cy를 가장 큰 값으로 두면 약간 위 박스가 이전 영역으로 빠질 수 있다.
    """
    sorted_boxes = sorted(body_boxes, key=lambda b: b["cy"])
    adjusted: list[_Marker] = []
    for m in area_markers:
        new_cy = m.cy
        if str(m.value) == "진로활동":
            for b in sorted_boxes:
                if b["cy"] < m.cy and b["text"].strip().startswith("희망분야"):
                    new_cy = b["cy"] - 5
                    break
        adjusted.append(_Marker(cy=new_cy, kind=m.kind, value=m.value))
    return adjusted


def _adjust_first_marker_by_body_gap(
    area_markers: list[_Marker],
    body_boxes: list[dict],
    prev_area: str | None,
    gap_threshold: float = 40.0,
) -> list[_Marker]:
    """페이지 첫 영역 마커가 셀 중간에 있어 본문 위쪽이 다른 영역과 섞이는 경우 보정.

    조건: prev_area가 있고(이전 페이지 영역 연속) 첫 마커 위쪽 본문 박스들 중 인접
    cy 갭이 임계값 이상인 곳이 있으면, 갭 직후 박스 cy로 첫 마커 cy를 조정한다.
    그러면 cy<조정값 박스는 prev_area로, cy>=조정값 박스는 첫 마커 영역으로 분류된다.
    """
    if not area_markers or prev_area is None:
        return area_markers
    sorted_markers = sorted(area_markers, key=lambda m: m.cy)
    first_marker = sorted_markers[0]
    above = sorted(
        [b for b in body_boxes if b["cy"] < first_marker.cy],
        key=lambda b: b["cy"],
    )
    if len(above) < 3:
        return area_markers
    cys = [b["cy"] for b in above]
    gaps = [(cys[i + 1] - cys[i], i) for i in range(len(cys) - 1)]
    max_gap, max_idx = max(gaps)
    if max_gap < gap_threshold:
        return area_markers
    new_cy = cys[max_idx + 1] - 5
    return [_Marker(cy=new_cy, kind=first_marker.kind, value=first_marker.value)] + sorted_markers[1:]


def _assign_area_per_box(
    body_boxes: list[dict], area_markers: list[_Marker], prev_area: str | None
) -> dict[str, list[dict]]:
    """본문 박스를 영역별로 분류.

    영역 마커 K개 → 본문을 K개 그룹으로 분할. 인접 마커 사이의 본문 박스 cy 갭 중
    가장 큰 위치를 그룹 경계로 사용한다 — OCR이 영역 마커를 셀 어디에 잡든(위·중앙·하단)
    영역 사이에는 본문 행간보다 약간 큰 갭이 반드시 존재한다는 표 구조 특성을 활용.
    첫 마커 위쪽 박스는 prev_area(이전 페이지 영역 연속) 또는 첫 영역. 영역 마커가
    없으면 페이지 전체가 prev_area.
    """
    out: dict[str, list[dict]] = {}
    if not body_boxes:
        return out
    if not area_markers:
        if prev_area:
            out[prev_area] = list(body_boxes)
        return out

    sorted_boxes = sorted(body_boxes, key=lambda b: b["cy"])
    sorted_markers = sorted(area_markers, key=lambda m: m.cy)

    boundaries: list[float] = []
    for i in range(len(sorted_markers) - 1):
        m1_cy = sorted_markers[i].cy
        m2_cy = sorted_markers[i + 1].cy
        best_pos = None
        best_gap = -1.0
        for j in range(len(sorted_boxes) - 1):
            b1_cy = sorted_boxes[j]["cy"]
            b2_cy = sorted_boxes[j + 1]["cy"]
            # b1_cy만 m1~m2 범위에 두어, 다음 영역 첫 박스가 m2를 살짝 넘는 경우(셀
            # 시작 박스가 마커보다 약간 아래)도 갭 후보로 포함시킨다.
            if m1_cy <= b1_cy < m2_cy:
                gap = b2_cy - b1_cy
                if gap > best_gap:
                    best_gap = gap
                    best_pos = (b1_cy + b2_cy) / 2.0
        if best_pos is None:
            best_pos = (m1_cy + m2_cy) / 2.0
        boundaries.append(best_pos)

    first_marker_cy = sorted_markers[0].cy
    above_first = prev_area if prev_area else str(sorted_markers[0].value)

    for b in sorted_boxes:
        cy = b["cy"]
        if cy < first_marker_cy:
            target = above_first
        else:
            idx = 0
            while idx < len(boundaries) and cy > boundaries[idx]:
                idx += 1
            target = str(sorted_markers[idx].value)
        out.setdefault(target, []).append(b)
    return out


def _grade_for_area(area_cy_range: tuple[float, float], grade_markers: list[_Marker], prev_grade: int) -> int:
    """영역의 cy 범위에 학년 마커가 들어 있으면 그 학년. 없으면 prev_grade."""
    lo, hi = area_cy_range
    for m in grade_markers:
        if lo <= m.cy <= hi:
            return int(m.value)  # type: ignore
    return prev_grade


def _time_for_area(area_cy: float, time_markers: list[_Marker]) -> int | None:
    """영역 마커 cy와 가장 가까운(±15px) 시간 마커. 없으면 None."""
    best = None
    best_d = 1e9
    for m in time_markers:
        d = abs(m.cy - area_cy)
        if d < 15 and d < best_d:
            best = int(m.value)  # type: ignore
            best_d = d
    return best


def _boxes_to_text(boxes: list[dict]) -> str:
    # 같은 행의 박스(cy 차이 작음)는 x_left 순으로 정렬되도록 cy를 10px로 라운딩.
    # 한 행 안에 "희망분야 | 교육분야" 같은 좌→우 컬럼 순서를 보존.
    boxes = sorted(boxes, key=lambda b: (b.get("page", 0), round(b["cy"] / 10) * 10, b["x_left"]))
    return " ".join(b["text"].strip() for b in boxes if b["text"].strip())


def _split_desired_field_boxes(boxes: list[dict]) -> tuple[str | None, list[dict]]:
    """진로활동 박스에서 '희망분야' 박스를 찾아 그 행 전체를 분리.

    같은 행 = 같은 페이지 + cy 차이 15px 이내. 행 박스들을 x_left 순으로 join한 텍스트가
    '희망분야 [구분자]? XXX' 형태면 XXX를 desired로, 그 행을 제외한 나머지를 본문으로.
    여러 페이지에 걸친 진로활동에서 희망분야가 첫 박스가 아닐 수도 있어 박스 리스트
    전체를 훑는다.
    """
    if not boxes:
        return None, boxes
    sorted_boxes = sorted(
        boxes, key=lambda b: (b.get("page", 0), b["cy"], b["x_left"])
    )

    desired_box = None
    for b in sorted_boxes:
        if b["text"].strip().startswith("희망분야"):
            desired_box = b
            break
    if desired_box is None:
        return None, sorted_boxes

    row_page = desired_box.get("page", 0)
    row_cy = desired_box["cy"]
    same_row: list[dict] = []
    rest: list[dict] = []
    for b in sorted_boxes:
        if b.get("page", 0) == row_page and abs(b["cy"] - row_cy) < 15:
            same_row.append(b)
        else:
            rest.append(b)

    same_row.sort(key=lambda b: b["x_left"])
    first_text = " ".join(b["text"].strip() for b in same_row).strip()
    m = DESIRED_FIELD_PAT.match(first_text)
    if not m:
        # '희망분야' 단독 행은 값이 비어있는 경우 — 그 박스도 본문에서 제외.
        # 그렇지 않으면 본문에 '희망분야' 텍스트가 잔재로 남는다.
        if DESIRED_FIELD_EMPTY_PAT.match(first_text):
            return None, rest
        return None, sorted_boxes
    desired = m.group(1).strip()
    return desired or None, rest


def extract(pages_json: list[dict], 창체_page_ids: list[int]) -> 창체결과:
    pages_map = {p["page"]: p for p in pages_json}
    creative_pages = [pages_map[i] for i in 창체_page_ids if i in pages_map]
    creative_pages.sort(key=lambda p: p["page"])

    # (학년, 영역) → 누적 본문 박스, 시간 (영역이 처음 등장한 학년에 시간이 한 번만 있음)
    bucket_boxes: dict[tuple[int, str], list[dict]] = {}
    bucket_time: dict[tuple[int, str], int | None] = {}

    prev_grade: int = 1
    prev_area: str | None = None

    for page in creative_pages:
        markers, body = _collect_markers_and_body(page)
        grade_ms = [m for m in markers if m.kind == "grade"]
        area_ms = [m for m in markers if m.kind == "area"]
        time_ms = [m for m in markers if m.kind == "time"]

        # 시간 매핑은 원본 영역 마커 cy로 (시간 마커가 영역 마커와 같은 행에 잡힘)
        area_time: dict[str, int | None] = {}
        for am in area_ms:
            area_time[str(am.value)] = _time_for_area(am.cy, time_ms)

        # 진로활동 마커 cy를 그 위쪽 '희망분야' 박스 cy로 조정 (셀 시작 정렬)
        area_ms = _adjust_career_marker(area_ms, body)
        # 페이지 첫 영역 마커가 셀 중간에 있고 본문에 큰 갭이 있으면 갭 직후로 보정 —
        # 이전 페이지 영역 연속이 다음 영역 본문 시작에 흡수되는 학년 경계 오류 방지.
        area_ms = _adjust_first_marker_by_body_gap(area_ms, body, prev_area)

        # 영역별 본문 분류 (조정된 마커 사용)
        by_area = _assign_area_per_box(body, area_ms, prev_area)

        # 학년 매핑: 영역 마커 cy ~ 다음 영역 마커 cy 사이에 있는 학년 마커로 갱신
        area_ms_sorted = sorted(area_ms, key=lambda m: m.cy)
        grade_ms_sorted = sorted(grade_ms, key=lambda m: m.cy)
        area_grade: dict[str, int] = {}
        current_grade = prev_grade
        CY_TOL = 20.0
        for i, am in enumerate(area_ms_sorted):
            next_cy = area_ms_sorted[i + 1].cy - CY_TOL if i + 1 < len(area_ms_sorted) else float("inf")
            for gm in grade_ms_sorted:
                if am.cy - CY_TOL <= gm.cy < next_cy:
                    current_grade = int(gm.value)  # type: ignore
                    break
            area_grade[str(am.value)] = current_grade

        # 영역을 cy 순서로 정렬(페이지 끝 prev_area 갱신용)
        areas_sorted = [(str(am.value), am.cy) for am in area_ms_sorted]

        # 누적
        for area, bxs in by_area.items():
            if area not in ALLOWED_AREAS:
                continue  # 봉사 등 제외
            grade = area_grade.get(area, prev_grade)
            key = (grade, area)
            bucket_boxes.setdefault(key, []).extend(bxs)
            # 시간은 같은 (학년, 영역)에 1회만 (영역 마커가 처음 등장한 페이지의 값)
            if key not in bucket_time:
                bucket_time[key] = area_time.get(area)

        # 페이지 끝: prev_area, prev_grade 갱신 (cy 가장 큰 영역의 학년/영역)
        if areas_sorted:
            last_area, _ = areas_sorted[-1]
            prev_area = last_area
            prev_grade = area_grade.get(last_area, prev_grade)

    # 결과 레코드 생성 (학년, 영역 ALLOWED_AREAS 순서)
    area_order = {a: i for i, a in enumerate(ALLOWED_AREAS)}
    sorted_keys = sorted(bucket_boxes.keys(), key=lambda k: (k[0], area_order.get(k[1], 99)))
    records: list[창체레코드] = []
    for key in sorted_keys:
        grade, area = key
        boxes = bucket_boxes[key]
        desired = None
        if area == "진로활동":
            desired, boxes = _split_desired_field_boxes(boxes)
        text = _boxes_to_text(boxes)
        if not text:
            continue
        records.append(창체레코드(
            학년=grade, 영역=area,
            시간=bucket_time.get(key),
            희망분야=desired,
            특기사항=text,
        ))
    return 창체결과(창체=records)


def main() -> None:
    stem = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STEM
    txt_path = Path(OUT_DIR) / f"{stem}.txt"
    json_path = Path(OUT_DIR) / f"{stem}.json"
    text = txt_path.read_text(encoding="utf-8")
    with json_path.open(encoding="utf-8") as f:
        pages_json = json.load(f)
    sections = split_sections(text)
    result = extract(pages_json, sections["창체"])
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
