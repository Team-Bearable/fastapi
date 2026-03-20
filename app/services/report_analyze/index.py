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

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "opinion": {"type": "string"},
                    },
                    "required": ["summary", "opinion"],
                    "additionalProperties": False,
                },
            }
        },
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

    parsed = json.loads(message.content[0].text)

    return {
        "summary": parsed["summary"],
        "opinion": parsed["opinion"],
    }
