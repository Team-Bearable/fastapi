"""생기부 jobType 별 처리기 — 요청 payload(dict) → 결과(dict).

입출력 모양은 생기부 LLM 통신 메세지 규약(189038594)을 따른다:
- RECORD_EXTRACT: {pdfFileUrl} → {records:[{section,grade,meta,content,sourcePageRange}]}
- ACTIVITY_EXTRACT: {sourceRecordId, content, section} → {activities:[{sourceSpan:{start,end}}]}
- TAGGING: {activityId, activityText, targetMajor} → {tags:{...}}
"""

from services.record_analyze.source_extraction import extract_source_records
from services.record_analyze.source_extraction.exceptions import (
    MissingSectionError,
    OcrError,
    UnsupportedRecordFormatError,
)
from services.record_analyze.activity_extraction import extract_activities
from services.record_analyze.tagging import extract_tags
from worker.errors import InvalidPayload, JobFailed


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


def handle_record_extract(payload: dict) -> dict:
    url = _require(payload, "pdfFileUrl")  # 필드 검증은 try 밖 — InvalidPayload 가 catch-all 에 안 먹히게
    try:
        records = extract_source_records(url)
    except UnsupportedRecordFormatError as e:
        raise JobFailed("UNSUPPORTED_RECORD_FORMAT", str(e))
    except MissingSectionError as e:
        raise JobFailed("MISSING_SECTION", str(e))
    except OcrError as e:
        raise JobFailed("OCR_FAILED", str(e))
    except Exception as e:
        # PDF 다운로드 실패 등 그 외 원문추출 실패. RECORD_EXTRACT 는 LLM 을 안 쓰므로
        # 기본 fallback(LLM_FAILED)이 부적합 — 전용 코드로 던진다.
        raise JobFailed("RECORD_EXTRACT_FAILED", str(e))
    for r in records:
        r["sourcePageRange"] = r.pop("source_page_range")
    return {"records": records}


async def handle_activity_extract(payload: dict) -> dict:
    content = _require(payload, "content")
    result = await extract_activities(content, _require(payload, "section"))
    # 활동은 content 의 연속 슬라이스라("".join==content 보장) 누적 오프셋으로 span 을 낸다.
    # 텍스트는 안 싣고 오프셋만 — 텍스트 = content[start:end] (규약 §4.2).
    activities = []
    pos = 0
    for act in result["activities"]:
        activities.append({"sourceSpan": {"start": pos, "end": pos + len(act)}})
        pos += len(act)
    return {"activities": activities}


async def handle_tagging(payload: dict) -> dict:
    result = await extract_tags(_require(payload, "activityText"), payload.get("targetMajor"))
    return {"tags": result["tags"]}
