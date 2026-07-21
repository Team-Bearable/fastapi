"""워드클라우드 jobType 처리기 — 요청 payload(dict) → 결과(dict).

Java WordCloudAiAdapter 와 맞춘 입출력:
- WORD_CLOUD: {keywords[], font, color, mask, uploadUrl}
  → PNG 을 생성해 uploadUrl(presigned PUT)로 업로드. 결과 본문 없음({}).

이미지 바이너리는 스트림에 싣지 않는다("메시지엔 본문 미포함" 원칙) — Java 가 발급한
presigned URL 로 워커가 직접 PUT 하고, 저장 위치 소유는 Java 가 유지한다.
"""

import requests

from app.services.word_cloud import generate_word_cloud
from app.worker.errors import InvalidPayload, JobFailed


def _require(payload: dict, key: str):
    try:
        return payload[key]
    except KeyError:
        raise InvalidPayload(f"missing field: {key!r}")


def _upload_png(url: str, data: bytes):
    r = requests.put(url, data=data, headers={"Content-Type": "image/png"}, timeout=60)
    r.raise_for_status()


def handle_word_cloud(payload: dict) -> dict:
    # 필드 검증은 try 밖 — InvalidPayload 가 catch-all 에 안 먹히게(saenggibu 패턴 동일).
    keywords = _require(payload, "keywords")
    if not keywords:  # 빈 키워드는 처리실패가 아니라 입력 계약 위반(원 라우터의 400 대응)
        raise InvalidPayload("empty keywords")
    font = _require(payload, "font")
    color = _require(payload, "color")
    mask = _require(payload, "mask")
    upload_url = _require(payload, "uploadUrl")
    try:
        img_buffer = generate_word_cloud(keywords, font=font, color=color, mask=mask)
        _upload_png(upload_url, img_buffer.getvalue())
    except Exception as e:
        # 워드클라우드는 LLM 을 안 쓰므로 기본 fallback(LLM_FAILED)이 부적합 — 전용 코드.
        raise JobFailed("WORD_CLOUD_FAILED", str(e))
    return {}
