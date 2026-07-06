"""좌표 기반 표 행 클러스터링.

Team-Bearable/ocr `ocr_paddle_table.cluster_rows` 이식. OCR 박스
`[(cy, x_left, height, text)]` 를 y로 행 클러스터링해 행별 ' | ' 결합 문자열로.
"""

ROW_TOL = 0.6  # 같은 행 판단: max(이전 줄 높이, 이번 박스 높이) × ROW_TOL


def cluster_rows(items, tol: float = ROW_TOL):
    """items: [(cy, cx_left, height, text), ...] → 행별 ' | ' 결합 문자열 리스트."""
    items = sorted(items, key=lambda i: (i[0], i[1]))
    rows: list[str] = []
    cur: list[tuple[float, str]] = []
    cur_y = None
    cur_h = None
    for cy, cx, h, t in items:
        if cur and cur_y is not None and cur_h is not None and abs(cy - cur_y) <= max(cur_h, h) * tol:
            cur.append((cx, t))
            cur_y = (cur_y * (len(cur) - 1) + cy) / len(cur)
            cur_h = max(cur_h, h)
        else:
            if cur:
                cur.sort()
                rows.append(" | ".join(t for _, t in cur))
            cur = [(cx, t)]
            cur_y = cy
            cur_h = h
    if cur:
        cur.sort()
        rows.append(" | ".join(t for _, t in cur))
    return rows
