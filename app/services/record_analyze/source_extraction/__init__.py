"""원문추출 — Vision OCR + 규칙 상태머신 → source_record[].

PDF(presigned URL) → Vision OCR → 좌표 표복원 → 규칙 추출기(창체/세특/행특)
→ source_record 딕셔너리 리스트. LLM 미사용·결정적·verbatim(원문 슬라이스).
"""

import requests

from .vision_ocr import ocr_pdf
from .rules import split_sections, extract_setuk, extract_changche, extract_haengtuk


def _download_pdf(url: str) -> bytes:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def extract_source_records(pdf_url: str) -> list[dict]:
    pdf_bytes = _download_pdf(pdf_url)
    return extract_from_bytes(pdf_bytes)


def extract_from_bytes(pdf_bytes: bytes) -> list[dict]:
    text, pages_json = ocr_pdf(pdf_bytes)
    sections = split_sections(text)
    records: list[dict] = []

    for r in extract_changche(pages_json, sections["창체"]).창체:
        records.append({
            "section": "CHANGCHE", "grade": r.학년,
            "meta": {"area": r.영역, "time": r.시간, "desiredField": r.희망분야},
            "content": r.특기사항, "source_page_range": sections["창체"],
        })
    for r in extract_setuk(text, sections["교과"], pages_json).세특:
        records.append({
            "section": "SETEUK", "grade": r.학년,
            "meta": {"subject": r.과목, "semester": r.학기, "subjectType": r.교과구분},
            "content": r.내용, "source_page_range": sections["교과"],
        })
    for r in extract_haengtuk(pages_json, sections["행특"]).행특:
        records.append({
            "section": "HAENGTEUK", "grade": r.학년, "meta": {},
            "content": r.내용, "source_page_range": sections["행특"],
        })
    return records
