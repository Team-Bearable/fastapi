"""Cloud Vision OCR → 규칙 추출기 입력(text, pages_json) 어댑터.

PDF를 페이지 이미지로 렌더(PyMuPDF, DPI 300) → Vision
`DOCUMENT_TEXT_DETECTION` 으로 문단+좌표 추출 → `cluster_rows` 로 표 행 복원해
Team-Bearable/ocr 규칙 상태머신이 먹는 동일 포맷(text: 행 ' | ' / 페이지 '\\f',
pages_json: 박스 좌표)을 만든다.
"""

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import fitz  # PyMuPDF
import requests
import google.auth
from google.auth.transport.requests import Request as GAuthRequest

from .exceptions import OcrError
from .rules import cluster_rows

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
DPI = 300  # 창체 학년 숫자 마커 검출 최소선
_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
_MAX_OCR_RETRIES = 3
_RETRY_INTERVAL = 5.0

_creds = None
_project = None


def _token() -> tuple[str, str]:
    global _creds, _project
    if _creds is None:
        _creds, _project = google.auth.default(scopes=_SCOPES)
    if not _creds.valid:
        _creds.refresh(GAuthRequest())
    return _creds.token, _project


def _para_text(para: dict) -> str:
    out: list[str] = []
    for word in para.get("words", []):
        for sym in word.get("symbols", []):
            out.append(sym.get("text", ""))
            brk = sym.get("property", {}).get("detectedBreak", {}).get("type", "")
            if brk in ("SPACE", "EOL_SURE_SPACE", "SURE_SPACE"):
                out.append(" ")
            elif brk in ("LINE_BREAK", "HYPHEN"):
                out.append("\n")
    return "".join(out)


def _para_box(para: dict) -> list[int]:
    bb = para.get("boundingBox", {})
    xs = [v.get("x", 0) for v in bb.get("vertices", [])]
    ys = [v.get("y", 0) for v in bb.get("vertices", [])]
    return [min(xs) if xs else 0, min(ys) if ys else 0, max(xs) if xs else 0, max(ys) if ys else 0]


def _ocr_page(png_bytes: bytes, token: str, project: str) -> Any | None:
    """한 페이지 Vision OCR. 일시 오류는 재시도하고 소진 시 OcrError."""
    body = {
        "requests": [{
            "image": {"content": base64.b64encode(png_bytes).decode()},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            "imageContext": {"languageHints": ["ko"]},
        }]
    }
    headers = {"Authorization": f"Bearer {token}", "x-goog-user-project": project,
               "Content-Type": "application/json"}
    for attempt in range(_MAX_OCR_RETRIES):
        try:
            r = requests.post(VISION_URL, json=body, headers=headers, timeout=90)
            r.raise_for_status()
            resp = r.json()["responses"][0]
            if "error" in resp:
                raise OcrError(f"Vision 응답 오류: {resp['error'].get('message', '')}")
            return resp
        except (requests.RequestException, OcrError) as e:
            if attempt == _MAX_OCR_RETRIES - 1:
                raise OcrError("Vision OCR 페이지 실패 (재시도 소진)") from e
            time.sleep(_RETRY_INTERVAL)
    return None


def _page_to_inputs(args):
    """한 페이지: Vision OCR → (cluster_rows 텍스트, box 리스트, W, H)."""
    png_bytes, token, project = args
    resp = _ocr_page(png_bytes, token, project)
    fta = resp.get("fullTextAnnotation", {})
    boxes: list[dict] = []
    w = h = 0
    for page in fta.get("pages", []):
        w, h = page.get("width", 0), page.get("height", 0)
        for block in page.get("blocks", []):
            for para in block.get("paragraphs", []):
                x0, y0, x1, y1 = _para_box(para)
                boxes.append({
                    "text": _para_text(para).strip(),
                    "x_left": float(x0), "x_right": float(x1),
                    "y_top": float(y0), "y_bottom": float(y1),
                    "cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0,
                    "w": float(x1 - x0), "h": float(y1 - y0),
                })
    items = [(b["cy"], b["x_left"], b["h"], b["text"]) for b in boxes]
    return "\n".join(cluster_rows(items)).strip(), boxes, w, h


def ocr_document(pdf_bytes: bytes, max_workers: int = 8) -> tuple[str, list[dict]]:
    """PDF 바이트 → (text, pages_json). 규칙 추출기 입력으로 바로 사용."""
    token, project = _token()  # 풀 바깥에서 1회 발급 (동시 refresh 레이스 방지)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pngs = [doc.load_page(i).get_pixmap(dpi=DPI).tobytes("png") for i in range(doc.page_count)]
    doc.close()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_page_to_inputs, [(p, token, project) for p in pngs]))
    page_texts = [r[0] for r in results]
    pages_json = [{"page": i + 1, "width": r[2], "height": r[3], "boxes": r[1]}
                  for i, r in enumerate(results)]
    text = ("\n\n" + chr(12) + "\n\n").join(page_texts)
    return text, pages_json
