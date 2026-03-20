import httpx
import base64
import json
import anthropic
import os
from typing import Optional
from dotenv import load_dotenv
from utils.analyze_prompt import SYSTEM, USER

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


async def download_pdf(presigned_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(presigned_url)
        response.raise_for_status()
        return response.content


async def analyze_report(
        presigned_url: str,
        topic: Optional[str] = None,
        master_category: Optional[str] = None,
        sub_category: Optional[str] = None,
        department: Optional[str] = None,
        major: Optional[str] = None,
) -> dict:
    pdf_bytes = await download_pdf(presigned_url)
    pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    user_message = USER.format(
        topic=topic or "",
        master_category=master_category or "",
        sub_category=sub_category or "",
        department=department or "",
        major=major or "",
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": user_message,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text

    parsed = json.loads(response_text)

    return {
        "summary": parsed.get("summary", ""),
        "opinion": parsed.get("opinion", ""),
    }
